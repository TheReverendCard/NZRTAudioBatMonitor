"""Pre-fit input integrity and explicit coverage. Input files and annotations remain read-only."""
import argparse,csv,hashlib,json,os,struct,sys,tempfile,wave
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from export_all import write
def filehash(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def audio(p):
    with wave.open(str(p)) as w:
        n=w.getnframes();channels=w.getnchannels();size=w.getsampwidth();rate=w.getframerate()
        if n<2048 or rate<96000 or w.getcomptype()!='NONE':raise ValueError('unsupported or too-short WAV')
        with p.open('rb') as f:
            head=f.read(12)
            if len(head)!=12 or head[:4]!=b'RIFF' or head[8:]!=b'WAVE' or struct.unpack_from('<I',head,4)[0]+8>p.stat().st_size:raise ValueError('truncated or invalid RIFF')
        hashpcm=hashlib.sha256();seen=0
        while b:=w.readframes(65536):seen+=len(b);hashpcm.update(b)
        if seen!=n*channels*size:raise ValueError(f'short payload: expected {n*channels*size}, read {seen}')
    q=p.with_suffix(p.suffix+'.json')
    if q.is_file():
        d=json.loads(q.read_text(encoding='utf-8-sig'))
        if d.get('capture_valid') in (False,0,'0') or any(d.get(k) not in (None,0,False,'0') for k in ('capture_errors','missing_samples','dropped_samples')):raise ValueError('receiver records invalid capture or missing samples')
        if d.get('pcm_bytes',seen)!=seen or d.get('pcm_sha256',hashpcm.hexdigest())!=hashpcm.hexdigest() or d.get('sample_rate',rate)!=rate or d.get('samples',n)!=n:raise ValueError('receiver receipt disagrees with PCM')
    return dict(samples=n,rate=rate,channels=channels,width=size)
def bitmap(p):
    # Force a complete decode with the trainer's Pillow; an unreadable image is never a negative.
    from PIL import Image
    with Image.open(p) as img:
        if img.format!='BMP' or 64 not in img.size or (img.height if img.width==64 else img.width)<8:raise ValueError('not a 64-bin bat BMP')
        img.load()
def safe(root,r):
    if not r:raise ValueError('missing input path')
    p=(root/r).resolve()
    if not p.is_relative_to(root):raise ValueError('outside collection root')
    return p
def guard(root,modalities):
    home=root/'Daily_Run_Reports'; rows=[];issues=0;totals=Counter();observed={};snapshot={}
    for mod in modalities:
        manifest=home/'Training_Phase1'/('wav_candidates.csv' if mod=='wav' else 'spectrogram_candidates.csv')
        try:
            snapshot[mod]=filehash(manifest)
            with manifest.open(encoding='utf-8-sig',newline='') as f:
                reader=csv.DictReader(f)
                required={'split','presence_class','confidence_grade','review_provenance','annotation_sha256','original_bmp',mod+'_eligible' if mod=='wav' else 'spectrogram_eligible'}
                if mod=='wav':required.add('original_wav')
                if required-set(reader.fieldnames or []):raise ValueError('unrecognised grade-first manifest')
                count=0
                for j,r in enumerate(reader,2):
                    rel=r.get('original_'+mod);status='excluded_by_snapshot';reason='';digest=None
                    flag=r.get('wav_eligible' if mod=='wav' else 'spectrogram_eligible')
                    if flag=='true' and r['split'] in ('train','validation','test'):
                        try:
                            label={'1':'negative','2':'negative','4':'positive','5':'positive'}.get(r['confidence_grade'])
                            if not label or label!=r['presence_class'] or (mod=='bmp' and r.get('usable_class')!=label) or r['review_provenance'] not in ('reviewed_confirmed','reviewed_metadata'):raise ValueError('label or reviewer provenance disagrees')
                            q=safe(root,r['original_bmp']+'.data')
                            if filehash(q)!=r['annotation_sha256']:raise ValueError('annotation changed')
                            p=safe(root,rel);before=p.stat();digest=filehash(p)
                            if mod=='wav':audio(p)
                            else:bitmap(p)
                            after=p.stat()
                            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('input changed during validation')
                            prior=observed.setdefault((mod,digest),(r['split'],label,j))
                            if prior[:2]!=(r['split'],label):raise ValueError('identical input has conflicting label or split')
                            status='valid' if prior[2]==j else 'duplicate';count+=1
                        except Exception as exc:status='unscorable';reason=str(exc);issues+=1
                    rows.append(dict(modality=mod,row=j,source=rel,status=status,reason=reason,source_sha256=digest));totals[mod+':'+status]+=1
                if not count:raise ValueError('no valid eligible inputs')
            data=manifest.read_bytes()
            if hashlib.sha256(data).hexdigest()!=snapshot[mod]:raise ValueError('manifest changed during validation')
            archive=home/'S3_Exports/Frozen_Manifests'/(snapshot[mod]+'.csv')
            archive.parent.mkdir(parents=True,exist_ok=True)
            if not archive.exists():
                with tempfile.NamedTemporaryFile(dir=archive.parent,delete=False) as temp:
                    temp.write(data)
                os.replace(temp.name,archive)
            if filehash(archive)!=snapshot[mod]:raise ValueError('archived manifest hash differs')
        except Exception as exc:rows.append(dict(modality=mod,status='manifest_error',reason=str(exc)));issues+=1
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');store=home/'S3_Exports/Training_Integrity'
    receipt=dict(schema=1,run=stamp,status='blocked' if issues else 'passed',issues=issues,counts=dict(totals),manifest_sha256=snapshot,rows=rows)
    write(store/(stamp+'.json'),receipt);write(store/'latest.json',{k:v for k,v in receipt.items() if k!='rows'})
    print('Training integrity:',receipt['status'],dict(totals),'Details:',store/(stamp+'.json'),flush=True);return int(bool(issues))
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--modalities',nargs='+',choices=['bmp','wav'],required=True);v=a.parse_args();sys.exit(guard(v.root.resolve(),v.modalities))
