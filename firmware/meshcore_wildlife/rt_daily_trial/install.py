"""Install the daily trial stage alongside the local review-first pipeline."""
from pathlib import Path
import argparse
import os
import shutil
import tempfile

HERE=Path(__file__).resolve().parent
ANCHOR='        open_report_pages(root)\n        print(f"Run Daily complete in '
HOOK='''        # PASS-1 daily trial, after review and reports, inside the daily lock.
        with state.timed("RT first-pass field trial"):
            trial = subprocess.run([sys.executable, str(TOOL/"RT_First_Pass"/"rt_trial.py"), str(root)])
            if trial.returncode:
                print("RT first-pass trial incomplete. See Daily_Run_Reports/RT_First_Pass/last_error.txt.")
'''
def write(path,data):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
        f.write(data)
        tmp=Path(f.name)
    try:os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
def install(tool,remove):
    p=tool/'review_first_daily.py'
    orig=p.read_bytes()
    text=orig.decode('utf8').replace('\r\n','\n')
    if remove:
        result=text.replace(HOOK,'')
    else:
        if text.count(ANCHOR)!=1:raise ValueError('Daily completion hook not recognised: '+str(p))
        result=text if HOOK in text else text.replace(ANCHOR,HOOK+ANCHOR)
    compile(result,str(p),'exec')
    if not remove:
        dest=tool/'RT_First_Pass'
        dest.mkdir(exist_ok=True)
        for name in ('features.py','audible.py','winner.json','rt_trial.py','replay.json','README.md'):
            write(dest/name,(HERE/name).read_bytes())
    if result!=text:
        backup=p.with_name('review_first_daily.before_rt_trial.py')
        if not remove and not backup.exists():shutil.copy2(p,backup)
        if p.read_bytes()!=orig:raise RuntimeError('Daily changed during installation')
        write(p,result.replace('\n','\r\n' if b'\r\n' in orig else '\n').encode())
    print('Daily trial hook removed.' if remove else 'Daily trial installed in '+str(tool))
if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--tool',type=Path,default=Path.home()/'Documents/Bat/BatDailyTool')
    ap.add_argument('--remove',action='store_true')
    a=ap.parse_args()
    install(a.tool,a.remove)
