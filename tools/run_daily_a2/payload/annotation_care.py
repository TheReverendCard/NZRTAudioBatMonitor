"""Conservative Xiao annotation migration, immutable first-pass snapshots and review state.

No recognition/training. Never infer that a pre-existing reviewed annotation is an
original machine prediction. All history is retained on collision.
"""
import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

REVIEWER = 'Jesse Card - Untrained'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    try:
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return default


def _no_links(path):
    path = Path(path)
    if path.is_symlink():
        return False
    if os.name == 'nt':
        import stat
        if path.stat().st_file_attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
            return False
    return True


def recorder_folders(root, day=None):
    root = Path(root)
    if day:
        dates = [root / day]
    else:
        dates = [d for d in sorted(root.iterdir()) if d.is_dir() and re.fullmatch(r'\d{8}', d.name) and _no_links(d)]
    for d in dates:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_dir() and _no_links(f) and re.fullmatch(r'(?:AR4|Xiao)\d{8}', f.name, re.I):
                yield f


def migrate_xiao(root, day=None):
    """Move complete legacy BMP bundles into source-WAV daily folder.

    If any destination conflicts or source WAV is missing, leave the entire
    bundle in place and log a warning, rather than guessing which sidecar won.
    """
    root = Path(root)
    days = [day] if day else [x.name for x in sorted(root.glob('[0-9]'*8)) if x.is_dir()]
    report = {'moved': 0, 'identical_removed': 0, 'conflicts': [], 'missing_wav': [], 'days': []}
    legacy = root/'AviaNZ_Experimental'
    for d in days:
        if not re.fullmatch(r'\d{8}', str(d)):
            continue
        src = legacy / d
        if not src.is_dir() or not _no_links(src):
            continue
        dst = root / d / ('Xiao' + d)
        if not dst.is_dir() or not _no_links(dst):
            report['conflicts'].append(f'{src}: canonical Xiao folder is missing or unsafe')
            continue
        report['days'].append(d)
        for bmp in sorted(src.glob('*.bmp')):
            if not bmp.is_file() or not _no_links(bmp):
                continue
            if not (dst/(bmp.stem+'.wav')).is_file():
                report['missing_wav'].append(str(bmp))
                continue
            parts = [p for p in (bmp, Path(str(bmp)+'.data'), src/(bmp.stem+'.conversion.json')) if p.is_file()]
            # If any output differs, don't move any part of the recording.
            conflicts = [p for p in parts if (dst/p.name).exists() and (not (dst/p.name).is_file() or digest(p)!=digest(dst/p.name))]
            if conflicts:
                report['conflicts'].append(f'{bmp}: different destination file(s): '+', '.join(p.name for p in conflicts))
                continue
            # Pre-copy to temp then atomically place the output, prior to source cleanup.
            # An interruption leaves the original intact and an exact-copy rerun is safe.
            for p in parts:
                target = dst/p.name
                if not target.exists():
                    tmp = dst/(p.name+'.migrate-'+uuid.uuid4().hex)
                    try:
                        shutil.copy2(p, tmp)
                        if digest(p)!=digest(tmp):
                            raise OSError('Migration hash mismatch for '+str(p))
                        if target.exists():
                            if digest(target)!=digest(p):
                                raise FileExistsError('Concurrent conflict: '+str(target))
                        else:
                            os.replace(tmp,target)
                    finally:
                        tmp.unlink(missing_ok=True)
            # Only delete source files whose new locations are all proven identical.
            for p in parts:
                if digest(p) != digest(dst/p.name):
                    raise OSError('Source differs after migration: '+str(p))
            for p in parts:
                p.unlink()
                report['moved'] += 1
        # Do not move legacy summaries/other metadata. Old folder remains as a
        # recoverable archive of any unresolved/undocumented leftovers.
    return report


def machine_snapshot(bmp, *, engine, origin, batch_id=None, source_data=None):
    """Backup only a sidecar produced in the current proven machine batch.

    Never call on pre-existing sidecars just because they have Operator=Auto.
    """
    bmp = Path(bmp)
    side = Path(source_data) if source_data is not None else Path(str(bmp)+'.data')
    if not side.exists():
        raise FileNotFoundError(side)
    # Verify basic JSON before backing up. Full annotation validation is done
    # separately by the daily pipeline.
    value = json.loads(side.read_text(encoding='utf-8-sig'))
    if not isinstance(value,list) or not value or not isinstance(value[0],dict):
        raise ValueError('Invalid machine annotation: '+str(side))
    dest = bmp.parent/'Backup'
    dest.mkdir(exist_ok=True)
    backup = dest/(bmp.name+'.data')
    manifest = dest/'manifest.json'
    info = read_json(manifest,{'version':1,'files':{}})
    bmp_hash=digest(bmp)
    observed=digest(side)
    record=info['files'].get(backup.name)
    if backup.exists():
        archive_hash=digest(backup)
        if record:
            if record.get('annotation_sha256')!=archive_hash or record.get('source_bmp_sha256')!=bmp_hash:
                raise ValueError('Baseline manifest mismatch; preserved for investigation: '+str(backup))
            return {'status':'already_identical' if archive_hash==observed else 'existing_baseline_preserved','backup':str(backup)}
        # A pre-existing unreceipted file cannot become an authentic first pass here.
        raise ValueError('Baseline exists without provenance receipt; preserved for reconciliation: '+str(backup))
    if record:
        raise ValueError('Baseline receipt exists but file is missing: '+str(backup))
    temp = dest/(side.name+'.pending-'+uuid.uuid4().hex)
    try:
        shutil.copy2(side,temp)
        if digest(temp)!=observed or digest(side)!=observed:
            raise OSError('Machine annotation changed during snapshot: '+str(side))
        # Exclusive publication of a complete file on NTFS. Never truncate an existing backup.
        os.link(temp,backup)
    finally:
        temp.unlink(missing_ok=True)
    info['files'][backup.name] = {
        'origin':origin, 'engine':engine, 'batch_id':batch_id,
        'source_bmp_sha256':bmp_hash, 'annotation_sha256':observed,
        'captured_utc':stamp(),
    }
    write_json(manifest,info)
    return {'status':'created','backup':str(backup)}


def missing_baselines(root):
    missing=[]
    for folder in recorder_folders(root):
        for bmp in sorted(folder.glob('*.bmp')):
            side=Path(str(bmp)+'.data')
            if side.is_file() and not (folder/'Backup'/side.name).is_file():
                missing.append(str(side))
    return missing


def reviewer_status(path, ledger=None, root=None):
    """A nonmatching Reviewer is NOT automatically an accepted human review."""
    path=Path(path)
    if not path.is_file():
        return 'no_annotation', ''
    try:
        # Use the same structure validation as the existing daily summary so
        # a corrupt annotation never becomes a human-reviewed training source.
        from cumulative_summary import annotation
        data, _processed = annotation(path)
        header=data[0]
        who=header.get('Reviewer') or ''
        operator=header.get('Operator') or ''
        if not isinstance(who,str) or not isinstance(operator,str):
            return 'invalid_annotation',''
        # User-stated exact marker, with Operator either empty or Auto.
        if who == REVIEWER and operator.strip() in ('','Auto'):
            return 'reviewed_metadata',who
        if ledger is not None and root is not None:
            key=path.relative_to(root).as_posix()
            rec=ledger.get('files',{}).get(key,{})
            if rec.get('sha256')==digest(path) and rec.get('confirmed'):
                return 'reviewed_confirmed',who
        if who.strip():
            return 'reviewer_needs_confirmation',who
        return 'unreviewed',who
    except (OSError,ValueError,TypeError,KeyError):
        return 'invalid_annotation',''


def record_confirmation(root, sides, *, reason, ledger_path=None):
    root=Path(root)
    ledger_path=ledger_path or (root/'Daily_Run_Reports'/'Review_Status'/'ledger.json')
    ledger=read_json(ledger_path,{'version':1,'files':{}})
    for side in sides:
        side=Path(side)
        if not side.is_file() or not side.resolve().is_relative_to(root.resolve()):
            raise ValueError('Cannot confirm missing/outside source annotation: '+str(side))
        ledger['files'][side.relative_to(root).as_posix()]={
            'sha256':digest(side), 'confirmed':True,
            'reason':reason, 'confirmed_utc':stamp(),
        }
    write_json(ledger_path,ledger)
    return len(sides)


def scan_review(root):
    root=Path(root)
    ledger=read_json(root/'Daily_Run_Reports'/'Review_Status'/'ledger.json',{'files':{}})
    results=[]
    for folder in recorder_folders(root):
        bmps=sorted(folder.glob('*.bmp'))
        if not bmps:
            continue
        groups={'reviewed_metadata':[], 'reviewed_confirmed':[], 'reviewer_needs_confirmation':[], 'unreviewed':[], 'no_annotation':[], 'invalid_annotation':[]}
        for bmp in bmps:
            side=Path(str(bmp)+'.data')
            state,who=reviewer_status(side,ledger,root)
            groups[state].append((side,who))
        results.append((folder,groups))
    return results
