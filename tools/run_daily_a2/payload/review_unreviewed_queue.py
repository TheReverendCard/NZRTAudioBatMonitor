"""Resumable Fast Review queue across canonical and historical AR4 folders.

Creates NTFS HARD LINKS to BMPs (no media copies) and independent .bmp.data
working copies. Only an explicitly hotkey-graded recording is synced back,
with original-file conflict detection and an immutable pre-change archive.
Never touches the original AviaNZ machine-only Backup or model weights.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import annotation_care as care
from review_dataset import legacy_bulk_folders

REVIEWER = 'Jesse Card - Untrained'
QUEUEDIR = Path('Daily_Run_Reports') / 'FastReviewQueue'
VERSION = 1


def sha(path: Path) -> str:
    return care.digest(path)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_relative(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or any(x in ('.','..') for x in rel.parts):
        raise ValueError('Unsafe queue source path: ' + str(relative))
    path = root / rel
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Queue source path escapes Bat root: ' + str(path))
    return path


def human_grade(side: Path) -> int | None:
    if not side.is_file(): return None
    try:
        value = json.loads(side.read_text(encoding='utf-8-sig'))
        if not isinstance(value, list) or not value or not isinstance(value[0], dict): return None
        meta = value[0]
        rv = meta.get('BatDailyReview')
        if not isinstance(rv,dict) or meta.get('Reviewer') != REVIEWER: return None
        grade = rv.get('grade')
        if isinstance(grade,bool) or not isinstance(grade,int) or grade not in (1,2,3,4,5): return None
        if rv.get('reviewer') != REVIEWER or rv.get('source') != 'avianz_gui_hotkey': return None
        return grade
    except (OSError,ValueError,TypeError,UnicodeError):
        return None


class ReviewQueue:
    def __init__(self,root: Path,limit:int=150):
        self.root=root.expanduser().resolve()
        self.home=self.root/QUEUEDIR
        self.active=self.home/'Active'
        self.statepath=self.home/'queue_state.json'
        self.reportpath=self.home/'queue_report.json'
        self.limit=limit
        if not 1<=limit<=500:raise ValueError('Queue size must be 1..500')
        if not self.root.is_dir():raise FileNotFoundError('Bat root not found: '+str(self.root))

    def load(self):
        if not self.statepath.is_file():return {'schema':VERSION,'items':{}}
        state=json.loads(self.statepath.read_text(encoding='utf-8'))
        if state.get('schema')!=VERSION or not isinstance(state.get('items'),dict):
            raise ValueError('Unrecognised review queue state. Do not delete it; inspect before proceeding.')
        return state

    def write(self,state):
        self.home.mkdir(parents=True,exist_ok=True)
        care.write_json(self.statepath,state)

    def report(self,action,**kwargs):
        result={'at_utc':utc(),'action':action,**kwargs}
        care.write_json(self.reportpath,result)
        return result

    def sources(self):
        """No recursive scans: ignore Backup, model folders and queue itself."""
        folders=list(care.recorder_folders(self.root))+list(legacy_bulk_folders(self.root))
        folders.extend(f for f in self.root.glob('[0-9]'*8+'/XiaoRT*') if f.is_dir() and f.name=='XiaoRT'+f.parent.name and care._no_links(f.parent))
        seen=set()
        for folder in sorted(folders):
            if not care._no_links(folder):continue
            for bmp in sorted(folder.glob('*.bmp')):
                if not bmp.is_file() or not care._no_links(bmp):continue
                if folder.name.startswith('XiaoRT') and not bmp.with_suffix('.rt.json').is_file():continue
                source=bmp.relative_to(self.root).as_posix()
                if source in seen:continue
                seen.add(source)
                yield bmp,source

    def scan(self):
        ledger=care.read_json(self.root/'Daily_Run_Reports'/'Review_Status'/'ledger.json',{'files':{}})
        totals=Counter()
        manifests={}
        self.priority=set()
        self.source_counts={}
        self.scan_errors=[]
        pending=[]
        for bmp,rel in self.sources():
            side=Path(str(bmp)+'.data')
            state,who=care.reviewer_status(side,ledger,self.root)
            source=bmp.parent.relative_to(self.root).as_posix()
            totals[state]+=1
            if state=='invalid_annotation':
                self.scan_errors.append(rel+': invalid/unreadable annotation')
                continue
            grade=human_grade(side)
            if grade is not None and state in ('reviewed_metadata','reviewed_confirmed'):
                continue
            if (state in ('reviewed_metadata','reviewed_confirmed','reviewer_needs_confirmation')
                    and side.is_file()):
                data=json.loads(side.read_text(encoding='utf-8-sig'))
                # A reviewer/folder confirmation proves handling, not an empty recording's outcome.
                # Do not infer a bat label, or create a machine backup.
                if len(data)!=1 or data[0].get('BatDailyReview'):
                    if state=='reviewer_needs_confirmation' or data[0].get('BatDailyReview'):
                        self.scan_errors.append(rel+': conflicting or nonstandard review metadata')
                    continue
                # Owner's historical convention, only when machine backup is authenticated
                # against BOTH bytes and recording, and accepted reviewer removed the DK segment.
                if state in ('reviewed_metadata','reviewed_confirmed'):
                    backup=bmp.parent/'Backup'/side.name
                    if backup.is_file():
                        if bmp.parent not in manifests:
                            manifests[bmp.parent]=care.read_json(backup.parent/'manifest.json',{}).get('files',{})
                        receipt=manifests[bmp.parent].get(side.name,{})
                        if receipt.get('annotation_sha256')==sha(backup) and receipt.get('source_bmp_sha256')==sha(bmp):
                            baseline=json.loads(backup.read_text(encoding='utf-8-sig'))
                            if (isinstance(baseline,list) and len(baseline)>1 and
                                all(isinstance(seg,list) and len(seg)==5 and isinstance(seg[4],list)
                                    and seg[4] and all(isinstance(x,dict) and x.get('species')=="Don't Know"
                                    for x in seg[4]) for seg in baseline[1:])):
                                totals['resolved_legacy_deletion']+=1
                                continue
                self.priority.add(rel)
                tier='needs_identity_resolution'
            elif state in ('unreviewed','no_annotation'):
                if side.is_file():
                    hdr=json.loads(side.read_text(encoding='utf-8-sig'))[0]
                    if hdr.get('Operator') not in ('','Auto',None) or hdr.get('BatDailyReview'):
                        self.scan_errors.append(rel+': review/operator needs confirmation')
                        continue
                tier='ordinary'
            else:
                continue
            totals[tier]+=1
            self.source_counts.setdefault(source,Counter())[tier]+=1
            pending.append((bmp,rel))
        pending.sort(key=lambda pair:(pair[1] not in self.priority,pair[1].casefold(),pair[1]))
        return pending,dict(totals)

    def backlog(self,label):
        pending,totals=self.scan()
        state=self.load()
        ext=self.root/'External Data'
        partial=list(self.scan_errors)
        if ext.is_dir():
            partial.append('External Data intake not integrated in this patch; raw external sources excluded.')
        print(f'{label}: {"PARTIAL inventory" if partial else "configured recorder inventory"}; '
              f'{len(pending)} actionable; {len(self.priority)} identity resolution, '
              f'{len(pending)-len(self.priority)} ordinary; {len(state["items"])} staged (limit {self.limit}).',flush=True)
        for source,counts in sorted(self.source_counts.items()):print('  '+source+': '+str(dict(counts)))
        for msg in partial[:3]: print('  '+msg)
        care.write_json(self.home/'backlog.json',dict(timestamp=utc(),phase=label,
            status='partial' if partial else 'configured_sources',remaining=len(pending),
            by_folder=self.source_counts,by_state=totals,staged=len(state['items']),issues=partial))
        return pending

    def sync(self,abort_on_conflict=True):
        state=self.load()
        copied=[];conflicts=[];kept=[];unchanged=[]
        for key,item in list(state['items'].items()):
            staged=self.active/key
            shadowdata=Path(str(staged)+'.data')
            original=safe_relative(self.root,item['source'])
            original_data=Path(str(original)+'.data')
            if not original.is_file() or not staged.is_file() or not os.path.samefile(original,staged):
                conflicts.append({'source':item['source'],'reason':'missing_or_broken_hardlink'});continue
            if sha(original)!=item['source_bmp_sha']:
                conflicts.append({'source':item['source'],'reason':'original_bmp_modified'});continue
            stage_sha=sha(shadowdata) if shadowdata.is_file() else None
            if stage_sha == item.get('staged_data_sha'):
                # If another tool completed this review independently, retire
                # the unmodified shadow instead of leaving it forever.
                status,_=care.reviewer_status(original_data,
                    care.read_json(self.root/'Daily_Run_Reports'/'Review_Status'/'ledger.json',{'files':{}}),self.root)
                if status in ('reviewed_metadata','reviewed_confirmed') and human_grade(original_data) is not None:
                    self._retire(state,key)
                else:
                    kept.append(item['source'])
                continue
            grade=human_grade(shadowdata)
            if grade is None:
                kept.append(item['source'])
                continue
            original_sha=sha(original_data) if original_data.exists() else None
            # Retry after copy succeeds but before queue_state.json is saved.
            if original_sha==stage_sha:
                self._retire(state,key)
                unchanged.append(item['source'])
                continue
            if original_sha!=item.get('original_data_sha'):
                conflicts.append({'source':item['source'],'reason':'original_annotation_changed_since_queue_creation'});continue
            # Archive exact pre-review original bytes (if they existed).
            archive=self.home/'Original_Annotation_History'/hashlib.sha256(item['source'].encode()).hexdigest()[:16]
            archive.mkdir(parents=True,exist_ok=True)
            if original_data.exists():
                archivefile=archive/(original_sha+'.bmp.data')
                if not archivefile.exists():
                    shutil.copy2(original_data,archivefile)
                    if sha(archivefile)!=original_sha:raise IOError('Original archive SHA mismatch: '+str(archivefile))
                if sha(archivefile)!=original_sha: raise IOError('Prior review history mismatch; source untouched')
            # Atomic publish; the queue sidecar is an independent file, not a hard link.
            fd,temp=tempfile.mkstemp(prefix=original_data.name+'.queue_',dir=original_data.parent)
            os.close(fd)
            try:
                shutil.copy2(shadowdata,temp)
                if sha(Path(temp))!=stage_sha:raise IOError('Staging copy SHA mismatch')
                if (sha(original_data) if original_data.exists() else None)!=original_sha or sha(original)!=item['source_bmp_sha']:
                    raise RuntimeError('Source changed during review sync; original retained')
                os.replace(temp,original_data)
            finally:
                if os.path.exists(temp):os.unlink(temp)
            if sha(original_data)!=stage_sha:raise IOError('Published review SHA mismatch')
            self._retire(state,key)
            copied.append({'source':item['source'],'grade':grade})
            self.write(state)  # checkpoint after EACH successful source update
        self.write(state)
        out=self.report('sync',completed=len(copied)+len(unchanged),newly_saved=copied,
                        already_saved=unchanged,remaining=len(state['items']),conflicts=conflicts)
        if conflicts and abort_on_conflict:
            raise RuntimeError(f'{len(conflicts)} review queue conflict(s). Originals not overwritten. Check '+str(self.reportpath))
        return out

    def _retire(self,state,key):
        staged=self.active/key
        side=Path(str(staged)+'.data')
        # Do not blindly remove modified data if files were tampered with.
        if side.exists():side.unlink()
        if staged.exists():staged.unlink()  # unlink one name; original BMP survives
        state['items'].pop(key,None)

    def prepare(self):
        self.active.mkdir(parents=True,exist_ok=True)
        # Preserve staged work and stop on existing conflicts.
        sync_result=self.sync()
        pending,totals=self.scan()
        state=self.load()
        wanted={rel for _,rel in pending[:self.limit]}
        for key,item in list(state['items'].items()):
            if item['source'] in wanted: continue
            shadow=Path(str(self.active/key)+'.data')
            if (sha(shadow) if shadow.exists() else None)==item.get('staged_data_sha'):
                self._retire(state,key)
                self.write(state)
        already={item['source'] for item in state['items'].values()}
        new=[];errors=[]
        for original,rel in pending:
            if len(state['items'])>=self.limit:break
            if rel in already:continue
            oid=hashlib.sha256(rel.encode('utf-8')).hexdigest()[:12]
            stem=''.join(c if c.isalnum() or c in '_-' else '_' for c in original.stem)[:45]
            key=f'{0 if rel in self.priority else 1}_{stem}_{oid}.bmp'
            if key in state['items']:
                raise ValueError('Review queue source ID collision: '+rel)
            staged=self.active/key
            originals=Path(str(original)+'.data')
            shadow=Path(str(staged)+'.data')
            if staged.exists() or shadow.exists():
                errors.append({'source':rel,'error':'unexpected_preexisting_queue_file'});continue
            # Explicitly refuse copying BMPs; a failed NTFS hard link should
            # be reported, never silently become thousands of duplicate BMPs.
            try:
                os.link(original,staged)
                if not os.path.samefile(original,staged):raise IOError('Not a hardlink')
                original_sha=sha(original)
                side_sha=sha(originals) if originals.exists() else None
                if originals.exists():shutil.copy2(originals,shadow)
                state['items'][key]={'source':rel,'source_bmp_sha':original_sha,
                                     'original_data_sha':side_sha,
                                     'staged_data_sha':sha(shadow) if shadow.exists() else None,
                                     'created_utc':utc()}
                new.append(rel)
                self.write(state)
            except Exception as exc:
                if shadow.exists():shadow.unlink()
                if staged.exists():staged.unlink()
                errors.append({'source':rel,'error':str(exc)})
                # Most likely NTFS hard links unavailable: avoid thousands of errors.
                break
        out=self.report('prepare',pending_total=len(pending),review_status=totals,
                        queue_size=len(state['items']),newly_linked=len(new),errors=errors,
                        previous_sync=sync_result.get('completed',0))
        return out

    def open(self):
        self.backlog('Before review')
        out=self.prepare()
        if out['errors']:
            raise RuntimeError('Queue hardlink creation failed, no BMP copies made: '+str(out['errors'][0]))
        if not out['queue_size']:
            self.backlog('After reconciliation')
            if out['previous_sync']:self.rebuild()
            return 0
        state=self.load()
        key=min(state['items'],key=lambda k:(state['items'][k]['source'] not in self.priority,k))
        source=self.active/key
        print(f'Review queue: {out["queue_size"]} linked BMPs; {out["pending_total"]} pending overall.')
        print('Originals unchanged until Fast Review exits and a valid 1-5 grade is synced.')
        print('Opening',source)
        try:
            from fast_review_entrypoint import start
            returncode=start(self.root/'AviaNZ_CLI_Source_Test',source)
        finally:
            report=self.sync(abort_on_conflict=False)
            print('Queue sync:',report['completed'],'graded recording(s) saved to originals;',report['remaining'],'still in queue')
            if report['conflicts']:
                print('CONFLICTS: changes were NOT overwritten. See',self.reportpath)
            self.backlog('After review')
            if report['completed'] or out['previous_sync']:
                self.rebuild()
        return returncode or int(bool(report['conflicts']))

    def rebuild(self):
        import subprocess
        subprocess.run([sys.executable,str(Path(__file__).with_name('rebuild_timeline.py')),'--all'],check=True)



def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.home()/'Documents'/'Bat')
    p.add_argument('--limit',type=int,default=150)
    p.add_argument('--mode',choices=('open','prepare','sync','status'),default='open')
    a=p.parse_args(); queue=ReviewQueue(a.root,a.limit)
    from run_integrity import run_lock
    with run_lock(queue.root,'review queue'):
        return run_mode(a,queue)

def run_mode(a,queue):
    if a.mode=='open':return queue.open()
    elif a.mode=='prepare':print(json.dumps(queue.prepare(),indent=2))
    elif a.mode=='sync':
        result=queue.sync(); print(json.dumps(result,indent=2));queue.backlog('After sync')
        if result['completed']:queue.rebuild()
    else:
        pending,counts=queue.scan()
        print(json.dumps({'total_pending':len(pending),'by_review_state':counts,
               'currently_linked':len(queue.load()['items'])},indent=2))

if __name__=='__main__':sys.exit(main())
