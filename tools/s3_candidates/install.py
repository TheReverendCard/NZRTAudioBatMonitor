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
        result=s.replace(DAILY,HOOK+DAILY);compile(result,str(daily),'exec')
        put(daily,result.replace('\n','\r\n' if b'\r\n' in old else '\n').encode())
    dest=tool/'S3_Candidates'
    for name in ('export_all.py','generate.py','restricted_model.py','winner.json','README.md','VALIDATION.md','build_project.py','build_all.py'):
        put(dest/name,(HERE/name).read_bytes())
    for sub in ('component','bench'):
        for p in (HERE/sub).rglob('*'):
            if p.is_file():put(dest/p.relative_to(HERE),p.read_bytes())
    launchers=[]
    for d in (root/'TrainingWorkbench',root/'CNNWorkbench',root/'NNWorkbench'):
        for p in list(d.glob('*.bat'))+list(d.glob('*.cmd')):
            # Detect trainer invocation, not a Setup or audit-only launcher.
            b=p.read_bytes()
            if MARK.encode() in b:launchers.append(p);continue
            import re
            if not re.search(rb'(?im)^\s*[^:\r\n]*?(?:python(?:\.exe)?[" ]|"%\w+%")\s+[^\r\n]*(?:train_baseline_models|cnn_bmp_mil|nn_mlp[^"\s]*|train_[^"\s]*mlp[^"\s]*)\.py\b',b):continue
            # Keep existing user entrypoint, working directory, and exit code. Batch
            # files often contain early exits, so retain their contents in a sibling.
            orig=p.with_name(p.stem+'.before_s3'+p.suffix)
            if '.before_s3' in p.stem:continue
            if orig.exists() and orig.read_bytes()!=b:raise ValueError('Existing trainer backup differs: '+str(orig))
            put(orig,b)
            wrap='@echo off\r\n'+MARK+'\r\nsetlocal\r\ncall "%~dp0'+orig.name+'" %*\r\nif errorlevel 1 exit /b %errorlevel%\r\npy -3 "%~dp0..\\BatDailyTool\\S3_Candidates\\export_all.py" --root "%~dp0.."\r\nexit /b %errorlevel%\r\n'
            put(p,wrap.encode('ascii'));launchers.append(p)
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
    a=ap.parse_args();out=install(a.root.resolve());sys.exit(subprocess.call([sys.executable,str(out/'export_all.py'),'--root',str(a.root.resolve())]))
