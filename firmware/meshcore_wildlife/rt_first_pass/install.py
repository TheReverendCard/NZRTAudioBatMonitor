"""Apply or reverse the verified diff against deployed SHARE-1."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

def digest(text):
    return sha256(text.encode('utf8')).hexdigest()

def replace_bytes(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
        temp = Path(tmp.name)
    try:
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)

def install(project, restore):
    spec = json.loads(Path(__file__).with_name('changes.json').read_text())
    nzrt = project / 'nzrt'
    backup = project / '.nzrt-backups' / 'before-pass-1'
    changes = []
    for name, recipe in spec.items():
        path = nzrt / name
        original = path.read_bytes()
        text = path.read_text(encoding='utf8')
        current = digest(text)
        src = recipe['after' if restore else 'before']
        dst = recipe['before' if restore else 'after']
        saved = backup / name
        if current == dst:
            if not restore and (not saved.is_file() or digest(saved.read_text(encoding='utf8'))!=src):
                raise ValueError('Missing or mismatched rollback copy for '+name)
            continue
        if current != src:
            raise ValueError('Different firmware source in '+str(path)+'. No changes applied.')
        if restore:
            if digest(saved.read_text(encoding='utf8')) != dst:
                raise ValueError('Backup mismatch: '+name)
            replacement = saved.read_bytes()
        else:
            if saved.exists() and digest(saved.read_text(encoding='utf8'))!=src:
                raise ValueError('Different backup already present: '+name)
            lines=text.splitlines(keepends=True)
            for start,stop,addition in reversed(recipe['edits']):
                lines[start:stop] = [addition]
            result=''.join(lines)
            if digest(result)!=dst:
                raise ValueError('Release verification failed: '+name)
            replacement=result.replace('\n','\r\n' if b'\r\n' in original else '\n').encode()
        changes.append((path,saved,original,replacement))
    if not restore:
        backup.mkdir(parents=True,exist_ok=True)
        for path,saved,original,replacement in changes:
            if not saved.exists(): replace_bytes(saved,original)
    for path,saved,original,replacement in changes:
        replace_bytes(path,replacement)
    print('Sources restored to SHARE-1.' if restore else 'PASS-1 sources verified.')

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('project',type=Path)
    ap.add_argument('--restore',action='store_true')
    args=ap.parse_args()
    try: install(args.project,args.restore)
    except (OSError,ValueError) as exc: raise SystemExit(str(exc))
