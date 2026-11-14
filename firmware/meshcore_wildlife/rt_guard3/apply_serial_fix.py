"""Combined GUARD-3 serial and nobuild upload repair. No flashing by this installer."""
import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = {
    'upload_candidate.py': ('be2ddd2cb1b877fe30e3ae9365b76c4d8140ef07b3f84ed1012c3c276494da05',
                            '65ec580d4ef81bc730c722ca4914dec0e06f65ec2a165a5e89a416d260418c8b'),
    'serial_link.py': '563d590f0bbf0d70a1552d1acb3716c08a4069dbab6d3df5619e5d8d40824928',
    'merge_upload_fix.py': None,
}

def digest(data):
    # Accept normal Windows checkout line endings, preserve exact backup bytes.
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()

def locate(value):
    root = Path(value).expanduser().resolve()
    options = [root, root/'NZRT_GUARD3_Prep', root/'NZRT_GUARD3_Prep'/'NZRT_GUARD3_Prep']
    found = [p for p in options if (p/'upload_candidate.py').is_file() and
             (p/'prepare_build.py').is_file()]
    if len(found) != 1:
        raise ValueError('Choose the existing tools folder containing Backup and Upload.cmd and last_candidate.txt.')
    return found[0]

def apply(target, payload=HERE):
    target = locate(target)
    manifest = json.loads((payload/'serial_fix_manifest.json').read_text(encoding='utf8'))
    previous, replacement = {}, {}
    for name, old in OLD.items():
        dst, src = target/name, payload/name
        if dst.is_symlink() or src.is_symlink():
            raise ValueError('Refusing linked script: ' + name)
        replacement[name] = src.read_bytes()
        if digest(replacement[name]) != manifest['files'][name]:
            raise ValueError('Fix package checksum failed: ' + name)
        previous[name] = dst.read_bytes() if dst.exists() else None
        allowed = old if isinstance(old, tuple) else (old,)
        before_hash = digest(previous[name]) if previous[name] is not None else None
        if before_hash not in (*allowed, manifest['files'][name]):
            raise ValueError('Unrecognised installed script: ' + name + '. Nothing changed.')
    changed = [n for n in OLD if previous[n] is None or digest(previous[n]) != digest(replacement[n])]
    if not changed:
        print('Combined upload fix already installed. Run Backup and Upload.cmd from:', target)
        return None
    backup = target/'Tool_Backups'/('upload_fix_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True, exist_ok=False)
    receipt = {'status':'backed_up', 'target':str(target), 'files':{}}
    for name in changed:
        if previous[name] is not None: (backup/name).write_bytes(previous[name])
        receipt['files'][name] = {'before_sha256':hashlib.sha256(previous[name]).hexdigest() if previous[name] is not None else None,
                                'after_sha256':hashlib.sha256(replacement[name]).hexdigest()}
    rp = backup/'receipt.json'
    rp.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    done = []
    try:
        for name in changed:
            tmp = target/(name+'.serial_fix.tmp')
            # Never overwrite an unrelated temporary file from another run.
            with tmp.open('xb') as f:
                f.write(replacement[name])
            try:
                os.replace(tmp, target/name)
            finally:
                if tmp.exists(): tmp.unlink()
            done.append(name)
    except (Exception, KeyboardInterrupt):
        for name in done:
            if previous[name] is None: (target/name).unlink()
            else: shutil.copy2(backup/name, target/name)
        receipt['status'] = 'rolled_back'
        rp.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
        raise
    receipt['status'] = 'installed'
    rp.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    print('Combined upload fix installed.  Backup:', backup)
    print('Reuse your existing compiled candidate.  No rebuild or Install.cmd needed.')
    print('Run Backup and Upload.cmd from:', target)
    print('That uploader will also back up and repair the compiled project merge-bin.py before connecting.')
    return backup

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tools', type=Path)
    args = ap.parse_args()
    default = Path(os.getenv('NZRT_BAT_ROOT', Path.home()/'Documents'/'Bat'))/'Firmware'/'GUARD3_Tools'
    target = args.tools
    if target is None:
        answer = input(f'Existing GUARD3 tools folder [{default}]: ').strip().strip('"')
        target = Path(answer) if answer else default
    apply(target)

if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('STOPPED:', str(exc) or type(exc).__name__)
        sys.exit(1)
