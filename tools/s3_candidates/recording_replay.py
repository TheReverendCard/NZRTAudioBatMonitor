"""Private replay pack. Prepare with owner workbench Python, run with ESP-IDF Python. No uploads."""
import argparse, hashlib, json, math, os, secrets, shutil, sys, tempfile, wave
from pathlib import Path
from emulator_gate import configure,compile_run,exclusive,inventory,parse,sha,stamp
from export_all import write,read
from training_guard import audio,bitmap
def checkpoint(bundle,weights):
    m,_=inventory(bundle)
    if sha(weights)!=m['model_sha256']:raise ValueError('checkpoint does not match exported model')
    return m
def prepare(bundle,weights,paths,dest,cnn_script=None):
    import numpy as np
    m=checkpoint(bundle,weights);prof=m['profile']
    if prof not in ('wav_mlp','wav_lr','bmp_cnn'):raise ValueError('field pack currently supports WAV MLP/logistic or BMP CNN')
    dest.mkdir(parents=True,exist_ok=False);rows=[];cases=[]
    def add(blob,item,arr,expected,identity):
        raw=arr.tobytes()
        if blob.tell()+len(raw)>7000000:raise ValueError('7 MB bench image limit; split these inputs into smaller packs')
        cases.append(dict(source=item,offset=blob.tell(),bytes=len(raw),expected=float(expected),**identity));blob.write(raw)
    if prof=='bmp_cnn':
        import importlib.util,torch
        spec=importlib.util.spec_from_file_location('cnn_trainer',cnn_script);trainer=importlib.util.module_from_spec(spec);spec.loader.exec_module(trainer)
        state=torch.load(weights,map_location='cpu',weights_only=True);net=trainer.TinyMILCNN().eval();net.load_state_dict(state['state_dict'])
    else:
        from restricted_model import restricted_load
        from tests.reference_wav_features import wav_features
        from scipy.signal import resample_poly
        from scipy.io.wavfile import write as wavwrite
        model=restricted_load(weights)
    with (dest/'samples.bin').open('wb') as blob:
        for path in paths:
            row=dict(source=path.name,status='unscorable');rows.append(row);start=blob.tell();ncase=len(cases)
            try:
                row['source_sha256']=sha(path)
                if prof=='bmp_cnn':
                    bitmap(path);x=trainer.pack_windows(trainer.inspect_bmp(path),state['width'],state['max_windows']).astype('<f4')
                    with torch.no_grad():ref=torch.sigmoid(net(torch.from_numpy(x)[None,:])).item()
                    add(blob,path.name,x,ref,dict(windows=len(x)))
                else:
                    meta=audio(path);row['audio']=meta
                    if meta['rate'] not in (96000,192000) or meta['channels']!=1 or meta['width']!=2:raise ValueError('test needs 96/192 kHz mono PCM16')
                    with wave.open(str(path)) as wf:
                        offset=0
                        while offset<meta['samples']:
                            n=min(meta['rate']*2,meta['samples']-offset)
                            if n*192000//meta['rate']<4096:raise ValueError('tail shorter than model minimum, recording incomplete for replay')
                            x=np.frombuffer(wf.readframes(n),'<i2');assert len(x)==n
                            if meta['rate']==96000:x=np.clip(np.rint(resample_poly(x.astype('f4')/32768,2,1)*32768),-32768,32767).astype('<i2')
                            with tempfile.TemporaryDirectory() as t:
                                p=Path(t)/'r.wav';wavwrite(p,192000,x);v=wav_features(p);ref=model.predict_proba(v[None,:])[0,1]
                            add(blob,path.name,x,ref,dict(start_input_sample=offset,input_samples=n,rt_pcm_samples=len(x)));offset+=n
                row['status']='ready';row['cases']=len(cases)-ncase
            except Exception as e:
                blob.seek(start);blob.truncate();del cases[ncase:];row['reason']=str(e)
    pack=dict(schema=1,profile=prof,bundle_sha256=inventory(bundle)[1],input_sha256=sha(dest/'samples.bin'),threshold=m['threshold'],rows=rows,cases=cases)
    write(dest/'pack.json',pack);return pack
def replay(bundle,pack,out,emu,dsp,timeout):
    cfg=read(pack/'pack.json');prof=cfg['profile'];m,h=inventory(bundle);data=(pack/'samples.bin').read_bytes()
    if h!=cfg['bundle_sha256'] or m['profile']!=prof or hashlib.sha256(data).hexdigest()!=cfg['input_sha256']:raise ValueError('pack or export changed')
    cases=cfg['cases'];tag=secrets.token_hex(12);out.mkdir(parents=True,exist_ok=False)
    result=dict(profile=prof,source_model=m['model_sha256'],bundle_sha256=h,pack_sha256=sha(pack/'pack.json'),status='not_run',inputs=cfg['rows'],cases=[],promotion_ready=False)
    try:
        if not cases:raise ValueError('no scorable cases')
        main=configure(out/'project',dsp)
        for f in bundle.glob('*.hpp'):shutil.copy2(f,main/f.name)
        src='#include "candidate.hpp"\n#include "esp_heap_caps.h"\n#include <cstdio>\n#include <new>\n#include <cstring>\nusing namespace '+prof+';\nextern const unsigned char data[] asm("_binary_samples_bin_start");\n'
        # Embedded bytes are copied to aligned RAM before numerical kernels read them.
        offsets=[];sizes=[];end=0
        for c in cases:
            if c['offset']!=end or c['bytes']<=0 or not math.isfinite(c['expected']):raise ValueError('incomplete or invalid case')
            offsets.append(end);sizes.append(c['bytes']);end+=c['bytes']
        if end!=len(data):raise ValueError('pack input coverage mismatch')
        src+='const int offsets[]={'+','.join(map(str,offsets))+'},sizes[]={'+','.join(map(str,sizes))+'};\n'
        alloc='heap_caps_aligned_alloc(16,{},MALLOC_CAP_SPIRAM)'
        if prof=='bmp_cnn':
            init='auto* w=(Workspace*)'+alloc.format('sizeof(Workspace)')+';if(!w)return;new(w) Workspace;'
            calc='if(sizes[i]!=int(K*3*64*W*sizeof(float)))return;float v=score((float*)x,*w);'
        else:
            src+='#include "wav_frontend.hpp"\n'
            init='auto* w=(float*)'+alloc.format('bat_s3_wav::WORK_FLOATS*4')+';if(!w||!bat_s3::fft_init())return;'
            calc='float f[165];if(!bat_s3_wav::compute((const int16_t*)x,sizes[i]/2,w,f))return;float v=score(f);'
        src+='void run(){'+init+'for(unsigned i=0;i<sizeof(sizes)/sizeof(int);i++){auto* x='+alloc.format('sizes[i]')+';if(!x)return;memcpy(x,data+offsets[i],sizes[i]);'+calc+'printf("BAT_RESULT '+tag+' %u %.9g\\n",i,(double)v);heap_caps_free(x);}}\n'
        raw,img=compile_run(out/'project',main,src,tag,emu,Path(os.environ['IDF_PATH'])/'tools/idf.py',out,timeout,data)
        vs,errors=parse(raw,tag,[c['expected'] for c in cases],0)
        result.update(image_sha256=img,uart_sha256=sha(out/'uart.log'),max_abs_error=max(errors),emulator_sha256=sha(emu))
        tol=.005 if prof.startswith('wav') else .00002
        for c,v,err in zip(cases,vs,errors):
            result['cases'].append(dict(c,emulated=v,error=err,decision='candidate' if v>=m['threshold'] else 'below_threshold',agrees=(v>=m['threshold'])==(c['expected']>=m['threshold']),within_tolerance=err<=tol))
        result['status']='passed' if all(x['agrees'] and x['within_tolerance'] for x in result['cases']) else 'failed'
        if result['status']=='passed' and any(x['status']!='ready' for x in cfg['rows']):result['status']='partial_coverage'
    except Exception as e:result.update(status='failed',error=str(e))
    write(out/'receipt.json',result);print(result['status'],out/'receipt.json',flush=True);return int(result['status']!='passed')
if __name__=='__main__':
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('prepare');p.add_argument('bundle',type=Path);p.add_argument('weights',type=Path);p.add_argument('new_pack',type=Path);p.add_argument('media',nargs='+',type=Path);p.add_argument('--cnn-script',type=Path)
    p=sub.add_parser('run');p.add_argument('bundle',type=Path);p.add_argument('pack',type=Path);p.add_argument('new_out',type=Path);p.add_argument('--emu',type=Path,required=True);p.add_argument('--dsp',type=Path);p.add_argument('--timeout',default=600,type=int)
    a=ap.parse_args()
    if a.cmd=='prepare':
        pack=prepare(a.bundle,a.weights,a.media,a.new_pack,a.cnn_script);print('Inputs:',len(pack['rows']),'Prepared cases:',len(pack['cases']));sys.exit(int(any(r['status']!='ready' for r in pack['rows'])))
    sys.exit(replay(a.bundle,a.pack,a.new_out,a.emu.resolve(),a.dsp,a.timeout))
