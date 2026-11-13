"""Scan completed local training runs independently. Never stage, promote or flash."""
from pathlib import Path
import argparse,hashlib,json,math,os,re,shutil,subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent
FAMILIES={'bmp':('bmp_lr','baseline.joblib','model_report.json'),'wav':('wav_lr','baseline.joblib','model_report.json'),
          'bmp_sharedband':('bmp_shared_lr','baseline.joblib','model_report.json'),
          'nn_mlp_bmp':('bmp_mlp','candidate.joblib','report.json'),'nn_mlp_wav':('wav_mlp','candidate.joblib','report.json'),
          'cnn_bmp_mil':('bmp_cnn','candidate_state.pt','report.json')}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=p.parent,delete=False) as f:json.dump(obj,f,indent=2,allow_nan=False);f.write('\n')
    os.replace(f.name,p)
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def revision():
    return digest(''.join(sha(p) for p in [HERE/k for k in ('export_all.py','generate.py','restricted_model.py','component/idf_component.yml')]+sorted((HERE/'component').rglob('*.hpp'))))
def install_bundle(dest,make):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        hashes=read(dest/'files.json')
        if ('manifest.json' not in hashes or set(hashes)!={p.name for p in dest.iterdir() if p.name!='files.json'} or any(Path(k).name!=k or not (dest/k).is_file() or sha(dest/k)!=v for k,v in hashes.items())):raise ValueError('cached output changed: '+str(dest))
        return read(dest/'manifest.json')
    tmp=Path(tempfile.mkdtemp(dir=dest.parent))
    try:
        m=make(tmp);write(tmp/'manifest.json',m)
        write(tmp/'files.json',{p.name:sha(p) for p in tmp.iterdir()})
        tmp.rename(dest);return m
    finally:
        if tmp.exists():shutil.rmtree(tmp)
def copy_kernels(tmp):
    for p in (HERE/'component/include').glob('*.hpp'):shutil.copy2(p,tmp/p.name)
    shutil.copy2(HERE/'component/idf_component.yml',tmp/'esp_dsp.yml')
def classify(folder,state,report):
    kind=FAMILIES[folder][0];info=read(report)
    needed=('candidate_state_sha256' if kind=='bmp_cnn' else 'candidate_joblib_sha256' if kind.endswith('mlp') else 'model_sha256')
    if not re.fullmatch('[0-9a-f]{64}',str(info.get(needed))) or info[needed]!=sha(state):raise ValueError('model hash absent or differs from report')
    if info.get('model_family',info.get('family'))!=kind[:3]:raise ValueError('wrong modality')
    snapshot=info.get('input_manifest_sha256') or info.get('manifest_sha256')
    if not re.fullmatch('[0-9a-f]{64}',str(snapshot)):raise ValueError('unverified training snapshot')
    if kind=='bmp_cnn':
        if info.get('candidate')!='cnn_bmp_mil_v0.1':raise ValueError('unknown CNN preprocessing')
    else:
        feature='band_robust32_bmp_shared_bins_30_63_v1' if kind=='bmp_shared_lr' else 'band_robust32_v1'
        if info.get('feature_version')!=feature:raise ValueError('unknown feature schema')
    if kind=='bmp_shared_lr' and info.get('model_branch')!='shared_frequency_bmp':raise ValueError('wrong shared feature branch')
    t=info.get('validation_selected_threshold' if kind.endswith('mlp') else 'threshold')
    if type(t) not in (int,float) or not math.isfinite(t) or not 0<=t<=1:raise ValueError('invalid threshold')
    return kind,info,snapshot,t
def candidate(folder,state,report,home,root,inline=False):
    kind,info,snapshot,t=classify(folder,state,report)
    if re.fullmatch(r'\d{8}T\d{12}Z_[0-9a-f]{8}',state.parent.name) and not state.parent.name.endswith(snapshot[:8]):raise ValueError('training snapshot and run suffix differ')
    sh,rh=sha(state),sha(report)
    key=digest(sh+rh+revision()); dest=home/'candidates'/kind/key
    def make(tmp):
        envdir='CNNWorkbench' if kind=='bmp_cnn' else 'TrainingWorkbench'
        if inline:
            from generate import generate
            generate(state,tmp,kind,t,info)
        else:
            exe=root/envdir/'.venv'/'Scripts'/'python.exe'
            if not exe.is_file():raise ValueError('missing '+str(exe))
            subprocess.run([str(exe),str(HERE/'export_all.py'),'--worker',str(state),str(report),str(tmp),folder],check=True)
        if sha(state)!=sh or sha(report)!=rh:raise RuntimeError('trainer changed model or report during export; retry')
        copy_kernels(tmp)
        return dict(schema=1,profile=kind,target='esp32s3',model_sha256=sha(state),report_sha256=sha(report),
                    dataset_sha256=snapshot,feature_version=info.get('feature_version','bmp_mil_3channel_v1'),
                    feature_source_sha256=info.get('reused_baseline_feature_source_sha256') or info.get('feature_source_sha256') or info.get('baseline_feature_script_sha256'),
                    threshold=t,kernel='ESP-DSP aes3 aligned float dot products',input='preprocessed '+kind[:3]+' tensors',
                    wifi_weights_compatible=(tmp/'weights.bin').exists(),promotion_ready=False,status='source_exported',
                    gates=['matching recorder frontend','end-to-end replay','S3 build and board timing/heap','shadow field comparison','owner approval'])
    m=install_bundle(dest,make)
    return {'profile':kind,'bundle':dest.relative_to(home).as_posix(),'status':m['status'],'wifi_weights_compatible':m['wifi_weights_compatible']}
def profiles(home,root):
    # Use installed trial weights if present so a changed winner produces a different candidate.
    source=root/'BatDailyTool/RT_First_Pass/winner.json'
    source=source if source.is_file() else HERE/'winner.json'
    for name in ('legacy','audible','ultrasound_rise','low_side_check','both_checks','rt_score1','evolved'):
        if name=='evolved':
            win=read(source);w,b,t=win['weights'],win['bias'],win['threshold']
            if len(w)!=5 or any(len(v)!=3 for v in w) or len(b)!=3 or not all(type(n) in (int,float) and math.isfinite(n) and abs(n)<1e10 for n in [j for v in w for j in v]+b+[t]):raise ValueError('invalid evolved winner')
        key=digest(name+revision()+(sha(source) if name=='evolved' else ''));dest=home/'candidates'/name/key
        def make(tmp):
            copy_kernels(tmp)
            if name=='evolved':
                fd=lambda n:format(float(n),'.9e')+'f'
                weights=','.join('{'+','.join(map(fd,v))+'}' for v in w)
                (tmp/'winner.hpp').write_text('namespace evolved {constexpr float weights[5][3]={'+weights+'},bias[3]={'+','.join(map(fd,b))+'},threshold='+fd(t)+';}\n')
                shutil.copy2(source,tmp/'winner.json')
            return dict(schema=1,profile=name,target='esp32s3',status='source_exported',promotion_ready=False,
              source=('audible.replay' if name in ('ultrasound_rise','low_side_check','both_checks') else 'RT-SCORE-1' if name=='rt_score1' else 'PASS-1'),input=('192 kHz PCM and aligned legacy filtered window, noise, hot flag, event peak' if name=='rt_score1' else '192 kHz PCM'),
              winner_sha256=sha(source) if name=='evolved' else None,wifi_weights_compatible=False,
              integration=('score1.hpp: initialise shared FFT, check valid() before accepting output' if name=='rt_score1' else 'first_pass.hpp: preserve existing warmup, gap and event policy'))
        install_bundle(dest,make)
        yield dict(profile=name,status='source_exported',bundle=dest.relative_to(home).as_posix())
def scan(root,inline=False):
    base=root/'Daily_Run_Reports/Model_Experiments';home=base.parent/'S3_Exports'; rows=[];errors=0
    try:rows.extend(profiles(home,root))
    except Exception as e:rows.append(dict(profile='first_pass',status='blocked',reason=str(e)));errors+=1
    for folder in sorted(set(FAMILIES)|{p.name for p in base.glob('*') if p.is_dir()}):
        if folder not in FAMILIES:
            rows.append(dict(profile=folder,status='unsupported',reason='no registered S3 adapter'));continue
        kind,model,rep=FAMILIES[folder]; runs=sorted(p for p in (base/folder).glob('*') if p.is_dir())
        if not runs:rows.append(dict(profile=kind,status='no_local_run'))
        for run in runs:
            try:row=candidate(folder,run/model,run/rep,home,root,inline)
            except Exception as e:row=dict(profile=kind,status='blocked',reason=str(e));errors+=1
            rows.append(dict(row,run=run.name))
    rows.append(dict(profile='saved_clip',status='reference_only',reason='keep every recording: comparison control with no detector'))
    rows.append(dict(profile='stock_AviaNZ_NZ_Bats',status='desktop_reference_only'))
    write(home/'index.json',dict(schema=1,promotion_ready=False,rows=rows))
    from collections import Counter
    print('S3 exports:',dict(Counter(r['status'] for r in rows)),'See',home/'index.json',flush=True)
    return 1 if errors or any(r['status']=='unsupported' for r in rows) else 0
if __name__=='__main__':
    if sys.argv[1:2]==['--worker']:
        state,report,out=map(Path,sys.argv[2:5]);kind,info,s,t=classify(sys.argv[5],state,report)
        from generate import generate
        generate(state,out,kind,t,info)
    else:
        ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path.home()/'Documents/Bat')
        sys.exit(scan(ap.parse_args().root.resolve()))
