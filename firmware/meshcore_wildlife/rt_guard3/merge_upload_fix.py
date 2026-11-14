"""Repair the known MeshCore merge-bin import for PlatformIO nobuild uploads."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

OLD_SHA = '9a5b0a84da4980d2c8594ae70a4d15a0637cc570a0addcb2c676aa9f825841b1'
OLD_IMPORT = b'Import("env", "projenv")'
NEW_IMPORT = b'Import("env")'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def normal(data):
    return data.replace(b'\r\n', b'\n')

def ensure_merge_script(project):
    """Change only a pinned, unused projenv import. Preserve exact backup bytes."""
    project = Path(project)
    path = project/'merge-bin.py'
    if path.is_symlink() or not path.is_file():
        raise ValueError('Expected a regular merge-bin.py in the compiled candidate: '+str(path))
    original = path.read_bytes()
    normalized = normal(original)
    # Recognise both the original and this exact one-line repair. Other edits stop.
    restored = normalized.replace(NEW_IMPORT, OLD_IMPORT)
    if sha(normalized) == OLD_SHA:
        fixed = original.replace(OLD_IMPORT, NEW_IMPORT)
    elif normalized.count(NEW_IMPORT) == 1 and sha(restored) == OLD_SHA:
        return {'status':'already_fixed', 'path':str(path), 'sha256':sha(original)}
    else:
        raise ValueError('Unrecognised merge-bin.py; no serial connection or upload attempted. File: '+str(path))
    backup = project/'PreUpdate_Backup'/('merge_bin_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    backup.mkdir(parents=True, exist_ok=False)
    (backup/'merge-bin.py').write_bytes(original)
    receipt = {'status':'backed_up', 'path':str(path), 'backup':str(backup/'merge-bin.py'),
               'before_sha256':sha(original), 'sha256':sha(fixed),
               'change':'Remove unused projenv import; env and mergebin target retained.'}
    rp = backup/'receipt.json'
    rp.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    tmp = project/'merge-bin.py.guard3_fix.tmp'
    with tmp.open('xb') as f:
        f.write(fixed)
    try:
        os.replace(tmp, path)
    finally:
        if tmp.exists(): tmp.unlink()
    receipt['status'] = 'fixed'
    rp.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf8')
    print('Repaired merge-bin.py for upload.  Backup:', backup, flush=True)
    return receipt
