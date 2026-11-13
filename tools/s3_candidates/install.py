"""Install versioned sidecars. Preserve other agents' Daily/trainer edits."""
import argparse,hashlib,os,shutil,tempfile,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
DAILY='        open_report_pages(root)\n        print(f"Run Daily complete in '
HOOK='''        # S3 export sidecars: a failure is reported independently of recorder intake.
        try:
            with state.timed("S3 candidate exports"):
                import subprocess as s3process
                s3process.run([sys.executable, str(root/"BatDailyTool"/"S3_Candidates"/"export_all.py"), "--root", str(root)], check=True)
        except (OSError, s3process.CalledProcessError) as s3err:
            print("S3 export needs attention:", s3err, "See Daily_Run_Reports/S3_Exports/index.json.", flush=True)
'''
# Trainer scripts include frozen source hashes in model provenance. Leave
# them byte-identical. Attach a post-run wrapper to their Windows entrypoints.
MARK='rem S3_EXPORT_POSTRUN_V1'
NEWMARK='rem S3_EXPORT_GUARDED_V2'
OLDHOOK=HOOK
HOOK=HOOK.replace('export_all.py','export_and_queue.py')
def atomic(p,data):
    with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as f:f.write(data);tmp=Path(f.name)
    try:os.replace(tmp,p)
    finally:tmp.unlink(missing_ok=True)
def install(root):
    tool=root/'BatDailyTool';daily=tool/'review_first_daily.py'
    if not daily.is_file():raise ValueError('Missing '+str(daily))
    changes={};original={}
    def put(p,new):
        old=p.read_bytes() if p.exists() else None
        if old!=new:changes[p]=new;original[p]=old
    old=daily.read_bytes();s=old.decode('utf-8').replace('\r\n','\n')
    if s.count(DAILY)!=1:raise ValueError('Daily completion anchor changed; no files modified.')
    if HOOK not in s:
        result=s.replace(OLDHOOK,HOOK) if OLDHOOK in s else s.replace(DAILY,HOOK+DAILY);compile(result,str(daily),'exec')
        put(daily,result.replace('\n','\r\n' if b'\r\n' in old else '\n').encode())
    dest=tool/'S3_Candidates'
    for name in ('export_all.py','generate.py','restricted_model.py','winner.json','README.md','VALIDATION.md','build_project.py','build_all.py','emulator_gate.py','export_and_queue.py','training_guard.py','recording_replay.py','health_coverage.py','prediction_coverage.py','EMULATION.md','Configure Emulator.bat','Run Emulator.bat','tests/reference_wav_features.py','tests/__init__.py'):
        put(dest/name,(HERE/name).read_bytes())
    for sub in ('component','bench'):
        for p in (HERE/sub).rglob('*'):
            if p.is_file():put(dest/p.relative_to(HERE),p.read_bytes())
    launchers=[]
    for d in (root/'TrainingWorkbench',root/'CNNWorkbench',root/'NNWorkbench'):
        for p in list(d.glob('*.bat'))+list(d.glob('*.cmd')):
            # Detect trainer invocation, not a Setup or audit-only launcher.
            b=p.read_bytes()
            if any(x in p.stem for x in ('.before_s3','.guarded_s3')):continue
            import re
            rx=rb'(?im)^([ \t]*(?:"%\w+%"|"?[^:\r\n]*?python(?:\.exe)?"?|py(?: -3)?)[ \t]+[^\r\n]*?(?:train_baseline_models|cnn_bmp_mil|nn_mlp[^"\s]*|train_[^"\s]*mlp[^"\s]*)\.py\b[^\r\n]*)'
            orig=p.with_name(p.stem+'.before_s3'+p.suffix);safe=p.with_name(p.stem+'.guarded_s3'+p.suffix)
            oldwrap=MARK.encode() in b or NEWMARK.encode() in b
            if oldwrap and not orig.is_file():raise ValueError('Missing trainer backup: '+str(orig))
            raw=orig.read_bytes() if oldwrap else b
            if not re.search(rx,raw):continue
            if orig.exists() and orig.read_bytes()!=raw:raise ValueError('Existing trainer backup differs: '+str(orig))
            put(orig,raw)
            nl=b'\r\n' if b'\r\n' in raw else b'\n'
            def inject(match):
                line=match[1];low=line.lower()
                mods='bmp' if b'bmp' in low or b'cnn' in low else 'wav' if b'wav' in low else 'bmp wav'
                run=b'"%~dp0..\\TrainingWorkbench\\.venv\\Scripts\\python.exe" "%~dp0..\\BatDailyTool\\S3_Candidates\\training_guard.py" --root "%~dp0.." --modalities '+mods.encode()
                return run+nl+b'if errorlevel 1 exit /b 1'+nl+line
            put(safe,re.sub(rx,inject,raw))
            def wrapper(mark,name,export):
                return ('@echo off\r\n'+mark+'\r\nsetlocal\r\ncall "%~dp0'+name+'" %*\r\nif errorlevel 1 exit /b %errorlevel%\r\npy -3 "%~dp0..\\BatDailyTool\\S3_Candidates\\'+export+'" --root "%~dp0.."\r\nexit /b %errorlevel%\r\n').encode('ascii')
            wrap=wrapper(NEWMARK,safe.name,'export_and_queue.py')
            if oldwrap and b not in (wrap,wrapper(MARK,orig.name,'export_all.py')):raise ValueError('Trainer wrapper was edited; compare manually: '+str(p))
            put(p,wrap);launchers.append(p)
    batch=root/'Daily_Run_Reports'/'S3_Install_Backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for p,data in original.items():
        if data is not None:
            q=batch/p.relative_to(root);q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data)
    done=[]
    try:
        for p,data in changes.items():
            if (p.read_bytes() if p.exists() else None)!=original[p]:raise ValueError('Concurrent edit: '+str(p))
            p.parent.mkdir(parents=True,exist_ok=True);atomic(p,data);done.append(p)
    except BaseException:
        for p in reversed(done):
            if original[p] is None:p.unlink()
            else:atomic(p,original[p])
        raise
    print('S3 Daily export hook installed. Trainer launchers:',*[p.name for p in launchers],sep='\n')
    if changes:print('Previous files (when present):',batch)
    return dest
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path.home()/'Documents/Bat')
    a=ap.parse_args();out=install(a.root.resolve());sys.exit(subprocess.call([sys.executable,str(out/'export_and_queue.py'),'--root',str(a.root.resolve())]))
