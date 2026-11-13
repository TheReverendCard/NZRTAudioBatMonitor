"""Compare actual predictions to the same frozen snapshot used by a trainer. Read only."""
import csv,math
from collections import Counter
from pathlib import Path
from export_all import sha,write
def audit(manifest,expected_sha,predictions,mod):
    if not manifest.is_file() or sha(manifest)!=expected_sha:return dict(status='snapshot_unavailable_or_changed')
    if not predictions.is_file():return dict(status='predictions_unavailable')
    rows={};special=[];counts=Counter()
    with manifest.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r.get('spectrogram_eligible' if mod=='bmp' else 'wav_eligible')!='true' or r.get('split') not in ('train','validation','test'):continue
            if r.get('confidence_grade') not in ('1','2','4','5') or r.get('review_provenance') not in ('reviewed_confirmed','reviewed_metadata'):continue
            key=(r['original_'+mod].replace('\\','/'),r['split']);grade=int(r['confidence_grade'])
            if key in rows:special.append(dict(source=key[0],split=key[1],status='duplicate_manifest_source'))
            rows[key]=grade
    seen=set()
    with predictions.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            key=(r.get('source','').replace('\\','/'),r.get('split',''));decision=r.get('model_prediction') or r.get('prediction')
            status='scored'
            try:
                score=float(r.get('model_probability') or r.get('probability'));assert_score=math.isfinite(score) and 0<=score<=1
            except (TypeError,ValueError):score=None;assert_score=False
            if key not in rows:status='outside_manifest'
            elif key in seen:status='duplicate_prediction'
            elif not assert_score or decision not in ('bat','noise') or r.get('grade')!=str(rows[key]):status='invalid_prediction'
            elif rows[key]>=4 and decision=='noise':status='reviewed_positive_below_threshold'
            elif rows[key]<=2 and decision=='bat':status='reviewed_negative_flagged'
            seen.add(key);counts[key[1]+':'+status]+=1
            if status!='scored':special.append(dict(source=key[0],split=key[1],status=status,probability=score if assert_score else None))
    for k in sorted(set(rows)-seen):
        special.append(dict(source=k[0],split=k[1],grade=rows[k],status='no_prediction'));counts[k[1]+':no_prediction']+=1
    trouble=any(i['status'] not in ('reviewed_positive_below_threshold','reviewed_negative_flagged') for i in special)
    return dict(status='incomplete' if trouble or not rows else 'accounted',eligible_distinct=len(rows),counts=dict(counts),exceptions=special)
