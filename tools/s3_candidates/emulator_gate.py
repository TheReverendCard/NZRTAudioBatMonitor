"""Run a content-identified ESP32-S3 diagnostic in Espressif esp-emu. Never flashes a board."""
import argparse, contextlib, hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from export_all import read, write, sha

HERE=Path(__file__).resolve().parent
DSP='3c8ac0fdfec83740b783e200862c8d0c056de0ad'
PROFILES=['legacy','audible','ultrasound_rise','low_side_check','both_checks','rt_score1','evolved',
          'bmp_lr','bmp_shared_lr','bmp_mlp','bmp_cnn','wav_mlp','wav_lr']
def stamp():return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def output(command,**kw):return subprocess.check_output(command,stderr=subprocess.STDOUT,text=True,**kw)
def inventory(bundle):
    files=read(bundle/'files.json')
    if not files or 'manifest.json' not in files or set(files)!={x.name for x in bundle.iterdir() if x.name!='files.json'}:raise ValueError('bundle file list differs')
    if any(Path(k).name!=k or (bundle/k).is_symlink() or sha(bundle/k)!=h for k,h in files.items()):raise ValueError('bundle hash mismatch')
    return read(bundle/'manifest.json'),sha(bundle/'files.json')
def training_issues(report):
    warnings={}
    for k in ('source_validation_failures','feature_failures','invalid_sha_or_missing_media','skipped_changed_or_missing','extraction_errors','feature_errors','invalid'):
        v=report.get(k)
        if v:warnings[k]=len(v) if isinstance(v,(list,dict)) else v
    return warnings
def textfile(p,s):
    if not p.exists() or p.read_text()!=s:p.write_text(s)
def configure(p,dsp):
    main=p/'main';main.mkdir(parents=True,exist_ok=True)
    # Stable component name, including for a verified vendored checkout of any directory name.
    local=''
    if dsp:
        dsp=dsp.resolve()
        if output(['git','-C',str(dsp),'rev-parse','HEAD']).strip()!=DSP or output(['git','-C',str(dsp),'status','--porcelain','--untracked-files=all']).strip():raise ValueError('ESP-DSP must be a clean pinned checkout')
        if re.search(r'[;"$\n]',str(dsp)) or not re.fullmatch(r'[A-Za-z0-9_.-]+',dsp.name):raise ValueError('unsupported DSP directory name')
        local='set(EXTRA_COMPONENT_DIRS "'+dsp.as_posix()+'")\n'
        req=dsp.name;(main/'idf_component.yml').unlink(missing_ok=True)
    else:
        req=''; textfile(main/'idf_component.yml',(HERE/'component/idf_component.yml').read_text())
    textfile(p/'CMakeLists.txt','cmake_minimum_required(VERSION 3.16)\nset(COMPONENTS main)\n'+local+'include($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(recogniser_probe)\n')
    textfile(main/'CMakeLists.txt','idf_component_register(SRCS "probe.cpp" INCLUDE_DIRS "." REQUIRES esp_timer esp_psram heap '+req+' EMBED_FILES "samples.bin")\n')
    textfile(p/'sdkconfig.defaults','CONFIG_DSP_OPTIMIZED=y\nCONFIG_DSP_MAX_FFT_SIZE_4096=y\nCONFIG_SPIRAM=y\nCONFIG_SPIRAM_MODE_OCT=y\nCONFIG_ESP_MAIN_TASK_STACK_SIZE=16384\nCONFIG_ESP_TASK_WDT_INIT=n\nCONFIG_ESPTOOLPY_FLASHSIZE_8MB=y\nCONFIG_COMPILER_OPTIMIZATION_PERF=y\nCONFIG_PARTITION_TABLE_CUSTOM=y\nCONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"\n')
    textfile(p/'partitions.csv','nvs,data,nvs,0x9000,0x6000,\nphy_init,data,phy,0xf000,0x1000,\nfactory,app,factory,0x10000,0x7e0000,\n')
    return main
def code(profile,tag):
    inc='#include "first_pass.hpp"\n#include "esp_heap_caps.h"\n#include <cstdio>\n#include <cstdlib>\n#include <new>\n'
    emit='void emit(int i,float v){printf("BAT_RESULT %s %d %.9g\\n","'+tag+'",i,(double)v);}\n'
    if profile.endswith(('mlp','lr')) or profile=='bmp_cnn':inc+='#include "candidate.hpp"\nusing namespace '+profile+';\n'
    if profile=='bmp_cnn':
        body='auto* s=static_cast<Workspace*>(heap_caps_aligned_alloc(16,sizeof(Workspace),MALLOC_CAP_SPIRAM));auto* x=static_cast<float*>(heap_caps_aligned_alloc(16,sizeof(float)*3*64*W,MALLOC_CAP_SPIRAM));if(!s||!x)return;new(s)Workspace;for(int i=0;i<3*64*W;i++){x[i]=float(i%17)/16;}emit(0,window_logit(x,*s));'
    elif profile.endswith(('mlp','lr')):
        body='for(int i=0;i<4;i++){emit(i,score(probe[i]));}'
    else:
        inc+='#include "score1.hpp"\n' if profile=='rt_score1' else '#include "winner.hpp"\n' if profile=='evolved' else ''
        typ={'audible':'Audible','ultrasound_rise':'Replay<bat_s3::ReplayRule::Ultrasound>','low_side_check':'Replay<bat_s3::ReplayRule::LowSide>','both_checks':'Replay<bat_s3::ReplayRule::Both>','legacy':'Legacy','evolved':'Evolved'}.get(profile)
        inc+='alignas(16) static float x[3840];\n'
        if profile=='rt_score1':
            local='static bat_s3_score1::Analyzer s;'
            body='if(!bat_s3::fft_init())return;for(int k=0;k<3;k++){s.reset();for(int w=0;w<8;w++){for(int i=0;i<3840;++i){x[i]=(k==0?0.f:.4f*sinf(i*.40234375f*6.283185307f/2)+(k==2?.4f*sinf(i*.40234375f*6.283185307f/4):0.f));}s.window(x,x,.06f,w%3!=1);}auto f=s.finish(3.2f);if(!s.valid())return;emit(k*3,f.score);emit(k*3+1,f.bat_like);emit(k*3+2,f.harmonic_fraction);}'
        else:
            local='static bat_s3::'+typ+' s;'
            init='s.prime(x,3840);s.prime(x,3840);s.prime(x,1920);' if profile=='legacy' else '' if profile=='evolved' else 'if(!s.init())return;'
            check='hot=s.check(x);' if profile=='legacy' else 'hot=s.check(x,evolved::weights,evolved::bias,evolved::threshold);' if profile=='evolved' else 'if(!s.check(x,hot))return;'
            body=init+'unsigned seed=131;for(int w=0;w<164;w++){for(int i=0;i<3840;i++){seed=1664525u*seed+1013904223u;x[i]=.01f*(int(seed>>16)-32768)/32768.f;if(w==151||w==155||w==161)x[i]+=.3f*sinf(i*(w==155?.125f:.203125f)*6.283185307f);if(w==161)x[i]+=.9f*sinf(i*.03125f*6.283185307f);}bool hot=false;'+check+'emit(w,hot);}'
            # Two identical input streams separated by three explicitly missing windows.
            # Clear the PCM scratch before legacy prime and require a cold restart.
            body='for(int segment=0;segment<2;segment++){if(segment){for(int i=164;i<167;i++)emit(i,-1);s.reset();}for(float &v:x)v=0;'+body.replace('emit(w,hot);','emit(segment*167+w,hot);')+'}'
        body=local+body
    return inc+emit+'void run(){'+body+'}\n',body
def checks(bundle,prof,main,tag):
    m,_=inventory(bundle)
    for f in bundle.glob('*.hpp'):shutil.copyfile(f,main/f.name)
    src,_=code(prof,tag)
    if prof.endswith(('mlp','lr')) or prof=='bmp_cnn':
        t=(bundle/'candidate.hpp').read_text()
        if prof=='bmp_cnn':
            v=re.search(r'probe_logit=([^;]+);',t);expected=[float(v[1].rstrip('f'))]
        else:
            v=re.search(r'float expected\[4\]=\{([^{}]+)\}',t);expected=[float(i.rstrip('f')) for i in v[1].split(',')]
    else:
        # Portable reference, independent of the S3 instructions. Replays the identical inputs.
        with tempfile.TemporaryDirectory() as td:
            q=Path(td);cc=shutil.which('c++') or shutil.which('g++')
            if not cc:raise RuntimeError('missing C++ compiler for rule oracle')
            (q/'ref.cpp').write_text(src.replace('#include "esp_heap_caps.h"','')+'int main(){run();}\n')
            subprocess.run([cc,'-std=c++11','-O2','-I'+str(main),str(q/'ref.cpp'),'-o',str(q/'ref')],check=True)
            raw=output([str(q/'ref')]);expected=[float(x.split()[-1]) for x in raw.splitlines() if x.startswith('BAT_RESULT ')]
        if len(expected)!=(9 if prof=='rt_score1' else 331):raise ValueError('incomplete portable reference')
    if prof in ('legacy','evolved','audible','ultrasound_rise','low_side_check','both_checks'):
        if expected[164:167]!=[-1.]*3 or expected[:164]!=expected[167:]:raise ValueError('portable cold restart diverged after gap')
    return src,expected
def parse(log,tag,expected,tol):
    vals={};end=0
    for line in log.splitlines():
        if line.strip()=='BAT_END '+tag:end+=1
        if not line.startswith('BAT_RESULT '):continue
        _,receipt,idx,v=line.split()
        if receipt!=tag or int(idx) in vals:raise ValueError('wrong or duplicate guest result')
        vals[int(idx)]=float(v)
    lost=sorted(set(range(len(expected)))-set(vals))
    if end!=1 or lost or set(vals)!=set(range(len(expected))):raise ValueError(f'incomplete emulator run: {len(vals)}/{len(expected)} results; missing indices {lost[:12]}; end records={end}')
    if any(not math.isfinite(x) for x in (*vals.values(),*expected)):raise ValueError('nonfinite result')
    errors=[abs(vals[i]-w) for i,w in enumerate(expected)]
    return [vals[i] for i in range(len(expected))],errors
def compile_run(p,main,src,tag,emu,idf,logdir,timeout,blob=b'\0'):
    logdir.mkdir(parents=True,exist_ok=True)
    if len(blob)>7000000:raise ValueError('replay pack too large for bench flash')
    (main/'samples.bin').write_bytes(blob)
    (main/'probe.cpp').write_text(src+'extern "C" void app_main(){run();printf("BAT_END '+tag+'\\n");fflush(stdout);}\n')
    image=p/'build/merged_replay.bin';image.unlink(missing_ok=True)
    with (logdir/'build.log').open('w') as f:
        for args in (['-DIDF_TARGET=esp32s3','build'],['merge-bin','-o',str(image)]):
            subprocess.run([sys.executable,str(idf),*args],cwd=p,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=900)
    log=logdir/'uart.log'
    with log.open('wb') as f:
        subprocess.run([str(emu),'--chip','esp32s3','--psram-size','8M','--firmware',str(image),'--elf',str(p/'build/recogniser_probe.elf'),'--timeout',f'{timeout}s','--exit-on','BAT_END '+tag],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout+30)
    return log.read_text(errors='replace'),sha(image)
def run_index(index,out,emu,dsp=None,only=None,force=False):
    index=index.resolve();out=out.resolve(); out.mkdir(parents=True,exist_ok=True)
    idf=Path(os.environ.get('IDF_PATH','')).resolve()/'tools/idf.py'
    if not idf.is_file():raise RuntimeError('Activate ESP-IDF first')
    if not emu:raise RuntimeError('esp-emu is not installed')
    emu=Path(emu).resolve()
    version=output([str(emu),'--version']).splitlines()[-1].strip()
    version_id=re.search(r'esp-emu (\d+)\.(\d+)\.(\d+)',version)
    if not version_id or tuple(map(int,version_id.groups()))<(0,50,0):raise ValueError('esp-emu 0.50.0 or later required')
    env_id={'esp_emu':version,'emulator_sha256':sha(emu),'idf':output([sys.executable,str(idf),'--version']).strip(),'dsp_commit':DSP,
            'compiler':output(['xtensa-esp32s3-elf-g++','-dumpfullversion']).strip(),'test_sha256':sha(Path(__file__))}
    p=out/'project';p.mkdir(exist_ok=True);main=configure(p,dsp)
    rows=[];nfailed=0;execution=stamp()
    entries=read(index)['rows']; index_sha=sha(index)
    for r in entries:
        prof=r['profile']
        if only and prof not in only:continue
        if r['status']!='source_exported':
            rows.append(dict(r,emulator_status='unavailable' if prof in PROFILES or r['status'] in ('blocked','unsupported') else 'reference_only'))
            continue
        try:
            bundle=(index.parent/r['bundle']).resolve()
            if not bundle.is_relative_to(index.parent) or prof not in PROFILES:raise ValueError('unknown bundle')
            m,h=inventory(bundle)
            if m['profile']!=prof:raise ValueError('profile mismatch')
            key=digest(h+json.dumps(env_id,sort_keys=True))
            cached=out/'passed'/key/'result.json'
            if not force and cached.exists():
                v=read(cached);uart=cached.with_name('uart.log')
                if v.get('status')!='passed' or v.get('bundle_sha256')!=h or v.get('uart_sha256')!=sha(uart):raise ValueError('cached evidence changed')
            else:
                logdir=out/'runs'/execution/(prof+'_'+key[:12]);logdir.mkdir(parents=True,exist_ok=True)
                tag=key[:24];src,expected=checks(bundle,prof,main,tag)
                raw,img=compile_run(p,main,src,tag,emu,idf,logdir,180)
                vals,err=parse(raw,tag,expected,2e-5)
                if max(err)>2e-5:raise ValueError(f'numeric error {max(err):g} exceeds tolerance')
                if prof.endswith(('mlp','lr')) and any((v>=m['threshold'])!=(w>=m['threshold']) for v,w in zip(vals,expected)):raise ValueError('threshold decision mismatch')
                v=dict(status='passed',bundle_sha256=h,profile=prof,tests=len(vals),max_abs_error=max(err),image_sha256=img,uart_sha256=sha(logdir/'uart.log'),environment=env_id,promotion_ready=False,tested_utc=stamp())
                write(logdir/'result.json',v);cached.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(logdir/'uart.log',cached.with_name('uart.log'));write(cached,v)
            rows.append(dict(r,emulator_status='passed',checks=v['tests'],max_error=v['max_abs_error'],receipt=str(cached.relative_to(out))))
        except Exception as e:
            nfailed+=1;rows.append(dict(r,emulator_status='failed',error=str(e)))
        print(prof,rows[-1]['emulator_status'],rows[-1].get('error',''),flush=True)
        write(out/'in_progress.json',dict(run=execution,index_sha256=index_sha,rows=rows,complete=False))
    incomplete=any(x['emulator_status']=='unavailable' for x in rows)
    res=dict(schema=1,run=execution,complete=True,scope=sorted(only) if only else 'all',index_sha256=index_sha,rows=rows,environment=env_id,promotion_ready=False,
             status='needs_attention' if nfailed or incomplete or not any(x['emulator_status']=='passed' for x in rows) else 'passed')
    write(out/'runs'/execution/'summary.json',res);write(out/('latest_subset.json' if only else 'latest.json'),res)
    return int(res['status']!='passed')
@contextlib.contextmanager
def exclusive(out):
    # Linux/WSL: OS releases the lock after a crash; queued workers wait and
    # reuse passed receipts. Keep the inode so two workers cannot lock different files.
    import fcntl
    out.mkdir(parents=True,exist_ok=True)
    with (out/'worker.lock').open('a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('index',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--emu',default=shutil.which('esp-emu'));ap.add_argument('--dsp',type=Path);ap.add_argument('--only',nargs='+',choices=PROFILES);ap.add_argument('--force',action='store_true')
    a=ap.parse_args();out=a.out or a.index.parent/'Emulator'
    with exclusive(out):sys.exit(run_index(a.index,out,a.emu,a.dsp,a.only,a.force))
