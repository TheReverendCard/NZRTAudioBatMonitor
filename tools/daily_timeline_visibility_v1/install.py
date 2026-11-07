from pathlib import Path
import hashlib, shutil, sys, subprocess
from datetime import datetime, timezone
here=Path(__file__).resolve().parent
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path.home()/'Documents'/'Bat'
target=root/'BatDailyTool'
if not (target/'daily_timeline.py').is_file():
    root=Path(input('Full path to your Bat folder: ').strip().strip('"'));target=root/'BatDailyTool'
if (root/'.bat_daily_tool.lock').exists():
    raise SystemExit('Daily Run lock exists. Close/finish Daily Run before installing. No files changed.')
expected=(here/'source_sha256.txt').read_text().strip()
source=target/'daily_timeline.py'
new=here/'BatDailyTool'/'daily_timeline.py'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if not source.is_file() or digest(source) not in (expected,digest(new)):
    raise SystemExit('Installed timeline differs from the supplied source. No files changed. Send the current daily_timeline.py so newer changes can be preserved.')
for p in (here/'BatDailyTool').glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
backup=target/'Timeline_Backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup.mkdir(parents=True)
for p in (here/'BatDailyTool').glob('*.py'):
    dest=target/p.name
    if dest.exists():shutil.copy2(dest,backup/p.name)
    tmp=dest.with_suffix('.py.installing');shutil.copy2(p,tmp);tmp.replace(dest)
print('Installed. Backup:',backup)
python=target/'.venv'/'Scripts'/'python.exe'
result=subprocess.run([str(python) if python.exists() else sys.executable,str(target/'rebuild_timeline.py'),'--all'],cwd=target)
if result.returncode:raise SystemExit('Patch installed, but report rebuild failed. Copy the error above for diagnosis.')
print('Complete. Open Bat/Daily_Timeline/index.html and press Ctrl+F5.')
