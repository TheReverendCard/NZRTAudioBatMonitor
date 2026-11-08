import hashlib,json,sys,zipfile
from pathlib import Path
from install import here, norm, publish
sys.path.insert(0,str(here/'payload'))
from run_integrity import run_lock
def main():
    raw=sys.argv[1] if len(sys.argv)>1 else input('Paste the full path to the verified before.zip: ').strip().strip('"')
    zpath=Path(raw).resolve()
    if not zpath.is_file() or zpath.name!='before.zip' or zpath.parents[1].name!='Tool_Backups':raise ValueError('Select an updater-created before.zip')
    root=zpath.parents[2];folder=zpath.parent
    changed=json.loads((folder/'installed.json').read_text()); specs=json.loads((here/'manifest.json').read_text())
    with run_lock(root,'rollback'),zipfile.ZipFile(zpath) as z:
        original=json.loads(z.read('SHA256.json'));actions=[]
        for name in changed:
            if name not in specs or Path(name).name!=name:raise ValueError('Unexpected script name')
            p=root/'BatDailyTool'/name;rel='BatDailyTool/'+name
            data=z.read(rel) if rel in original else None
            if data is not None and hashlib.sha256(data).hexdigest()!=original[rel]:raise ValueError('Backup invalid for '+name)
            if (not p.exists() and data is None) or (p.exists() and data is not None and p.read_bytes()==data):continue
            if not p.is_file() or norm(p)!=specs[name]['new']:raise ValueError('Local script changed since update: '+name)
            actions.append((p,data))
        for p,data in actions:
            if data is None:p.unlink()
            else:publish(p,data)
        print('Restored',len(actions),'scripts. Field data and settings untouched.')
if __name__=='__main__':main()
