"""Owner-local installer. No network or third-party dependencies."""
import argparse, hashlib, json, os, shutil, sys, tempfile, zipfile
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
here=Path(__file__).resolve().parent
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def norm(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def publish(p,data):
    fd,n=tempfile.mkstemp(dir=p.parent);os.close(fd)
    try:
        Path(n).write_bytes(data);os.replace(n,p)
    finally:Path(n).unlink(missing_ok=True)
def backup(root,tool,where):
    # Local only: can contain settings/credentials. Exclude generated environments.
    def files():
        for base,dirs,names in os.walk(tool,onerror=lambda e: (_ for _ in ()).throw(e)):
            dirs[:]=[n for n in dirs if n not in {'.git','.venv','__pycache__'}]
            for n in dirs+names:
                p=Path(base)/n
                if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError(f'Back up linked path separately before updating: {p}')
            yield from (Path(base)/n for n in names)
        yield from (p for p in root.iterdir() if p.is_file() and p.suffix.lower() in ('.bat','.cmd','.ps1','.py'))
    before={}
    with zipfile.ZipFile(where,'x',zipfile.ZIP_DEFLATED) as z:
        for p in files():
            rel=p.relative_to(root).as_posix();before[rel]=digest(p);z.write(p,rel)
        z.writestr('SHA256.json',json.dumps(before,indent=2))
    with zipfile.ZipFile(where) as z:
        for rel,h in before.items():
            with z.open(rel) as f:
                chk=hashlib.sha256()
                for b in iter(lambda:f.read(1048576),b''):chk.update(b)
            if chk.hexdigest()!=h or digest(root/rel)!=h:raise IOError('Backup verification failed: '+rel)
    return before

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path.home()/'Documents'/'Bat')
    ap.add_argument('--apply',action='store_true');a=ap.parse_args();root=a.root.resolve();tool=root/'BatDailyTool'
    if not (tool/'daily_pipeline.py').is_file():raise SystemExit('BatDailyTool missing. Use --root with your Bat folder.')
    manifest=json.loads((here/'manifest.json').read_text())
    changes=[];blocked=[]
    for name,spec in manifest.items():
        src=here/'payload'/name;target=tool/name
        if norm(src)!=spec['new']:raise ValueError('Invalid package: '+name)
        compile(src.read_bytes(),name,'exec')
        if target.exists() and norm(target)==spec['new']:continue
        if (not target.exists() and spec['required']) or (target.exists() and norm(target) not in spec['old']):blocked.append(name)
        changes.append(name)
    print('Planned:',', '.join(changes) or 'already installed')
    if blocked:print('Different or missing local versions:',', '.join(blocked))
    if not a.apply:return
    sys.path.insert(0,str(here/'payload'));from run_integrity import run_lock
    with run_lock(root,'install Run Daily update'):
        folder=root/'Tool_Backups'/('RunDaily_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));folder.mkdir(parents=True)
        prior=backup(root,tool,folder/'before.zip')
        print('Verified private backup:',folder/'before.zip',flush=True)
        for name in changes:
            f=tool/name
            if f.exists() and norm(f) not in manifest[name]['old'] and name not in blocked:blocked.append(name)
        if blocked:raise SystemExit('STOPPED after backup. No run files changed. Supply the listed scripts for integration.')
        changed=[]
        try:
            for name in changes:
                dest=tool/name;rel='BatDailyTool/'+name
                if (digest(dest) if dest.exists() else None)!=prior.get(rel):raise RuntimeError('File changed during install: '+name)
                publish(dest,(here/'payload'/name).read_bytes());changed.append(name)
                if norm(dest)!=manifest[name]['new']:raise IOError('Verification failed: '+name)
        except BaseException:
            with zipfile.ZipFile(folder/'before.zip') as z:
                for name in reversed(changed):
                    rel='BatDailyTool/'+name
                    if rel in prior:publish(tool/name,z.read(rel))
                    else:(tool/name).unlink()
            raise
        (folder/'installed.json').write_text(json.dumps(changed))
        print('Installed. Use your existing Run Daily Scan and Review All Unreviewed launchers.')
if __name__=='__main__':main()
