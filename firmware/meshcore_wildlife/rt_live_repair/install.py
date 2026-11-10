"""Apply or roll back this four-file overlay in the owner's existing RT project."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
def digest(data):
    return hashlib.sha256(data).hexdigest()

def replace(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        tmp.write(data)
        staged = Path(tmp.name)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    target = args.project / 'nzrt'
    backup = args.project / '.nzrt-backups' / 'before-live-1'
    manifest = json.loads((HERE / 'hashes.json').read_text())
    changes = {}
    for name, hashes in manifest.items():
        path = target / name
        current = path.read_bytes()
        payload = (HERE / 'payload' / name).read_bytes()
        if digest(payload) != hashes['live']:
            raise SystemExit(f'Package checksum failed for {name}')
        if digest(current) not in hashes.values():
            raise SystemExit(f'Unexpected local version of {name}. No files changed.')
        before = backup / name
        if before.exists() and digest(before.read_bytes()) != hashes['original']:
            raise SystemExit(f'Backup checksum failed for {name}')
        if args.restore and digest(current) == hashes['original']:
            continue
        if digest(current) == hashes['live'] and not before.exists():
            raise SystemExit(f'Missing original backup for {name}')
        desired = before.read_bytes() if args.restore else payload
        if current != desired:
            changes[path] = (current, desired)
    backup.mkdir(parents=True, exist_ok=True)
    for path, (current, _) in changes.items():
        if not args.restore and not (backup / path.name).exists():
            replace(backup / path.name, current)
    done = []
    try:
        for path, (current, desired) in changes.items():
            replace(path, desired)
            done.append((path, current))
    except BaseException:
        for path, original in reversed(done):
            replace(path, original)
        raise
    print(f'{len(changes)} source files updated. Original copies in {backup}')
if __name__ == '__main__':
    main()
