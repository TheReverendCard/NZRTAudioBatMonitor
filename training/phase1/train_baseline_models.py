#!/usr/bin/env python3
"""Fit *experimental* BMP and WAV classifiers using frozen night-split labels.

These are first-generation sklearn baselines, NOT AviaNZ .h5 recognisers and NOT
ESP32 deployable models. Only reads original media and trusted frozen manifests;
never edits recordings, grades, recogniser weights or firmware.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
import sys
import wave
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import signal
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import joblib

from training_phase1 import load_csv, safe_rel, count_sha, determine_split

SEED=20261105
FEATURE_VERSION='band_robust32_v1'
MODELS=('bmp','wav')


def allowed_path(root: Path,rel:str) -> Path:
    p=(root/safe_rel(rel)).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('Source escapes Bat root: '+str(p))
    return p


def band_pools(array:np.ndarray) -> np.ndarray:
    """[frequency bands x time] -> fixed robust time-frequency feature vector."""
    if array.ndim != 2 or array.shape[0] < 12 or array.shape[1] < 1:
        raise ValueError('Invalid spectrogram dimensions: '+str(array.shape))
    # Bounded physical range, float32. Each band uses robust temporal
    # descriptors; does not label all temporal windows in a positive clip.
    bands=np.array_split(np.arange(array.shape[0]),32)
    vec=[]
    for ids in bands:
        band=array[ids]
        # foreground per frequency is relative to local temporal median
        baseline=np.median(band,axis=1,keepdims=True)
        excess=np.maximum(band-baseline,0.0)
        strength=np.max(excess,axis=0)
        vec.extend([float(np.mean(strength)),
                    float(np.percentile(strength,90)),
                    float(np.percentile(strength,99)),
                    float(np.max(strength)),
                    float(np.mean(strength>0.25))])
    vec.extend([float(np.mean(array)),float(np.std(array)),
                float(np.percentile(array,99)),float(np.max(array)),
                math.log1p(array.shape[1])])
    return np.asarray(vec,dtype=np.float32)


def bmp_features(path:Path)->np.ndarray:
    with Image.open(path) as im:
        if im.width == 64: arr=np.asarray(im.convert('L'),dtype=np.float32).T
        elif im.height == 64: arr=np.asarray(im.convert('L'),dtype=np.float32)
        else:raise ValueError('Not DOC 64-bin BMP: '+str(im.size))
    # AviaNZ's DOC reader reverses grayscale: dark means stronger.
    energy=(255.-arr)/255.
    # Remove the first/last column, which can contain rendering scale or
    # boundary artifacts, and the bottom placeholder bin if present.
    if energy.shape[1] > 4:energy=energy[:,1:-1]
    energy=energy[:-1]
    return band_pools(energy)


def wav_features(path:Path)->np.ndarray:
    """96k mono-equivalent WAV, 8..45kHz only, preserving actual bandwidth."""
    from scipy.io import wavfile
    fs,data=wavfile.read(path,mmap=False)
    if fs<96000:raise ValueError('WAV less than 96kHz: '+str(fs))
    if data.ndim==2:data=np.mean(data.astype(np.float32),axis=1)
    if data.ndim!=1:raise ValueError('Unsupported WAV dimensions')
    if data.size<2048:raise ValueError('Too-short WAV')
    if np.issubdtype(data.dtype,np.integer):
        data=data.astype(np.float32)/max(abs(np.iinfo(data.dtype).min),np.iinfo(data.dtype).max)
    else:data=np.asarray(data,dtype=np.float32)
    if fs!=96000:
        from math import gcd
        d=gcd(int(fs),96000)
        data=signal.resample_poly(data,96000//d,fs//d).astype(np.float32)
    # Bound runtime/memory; sample up to first 30s and track this cap in metadata.
    data=data[:30*96000]
    frequency,time,sg=signal.spectrogram(data,fs=96000,window='hann',
        nperseg=1024,noverlap=512,scaling='spectrum',mode='magnitude')
    selector=(frequency>=8000)&(frequency<=45000)
    if not selector.any():raise ValueError('No ultrasonic frequency bins')
    sg=sg[selector].astype(np.float32)
    # Relative log magnitude (dB-like), clipped to avoid numeric instability.
    log=np.log10(np.maximum(sg,1.e-8))
    background=np.median(log,axis=1,keepdims=True)
    excess=np.clip((log-background)*2.0,0.,3.)/3.
    return band_pools(excess)


def csv_rows(path):
    with path.open('r',newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def sample_manifest(path:Path,kind:str,root:Path):
    allrows=csv_rows(path)
    chosen=[];seen_sha={};duplicates=[];invalid=[]
    for row in allrows:
        if row.get('split') not in ('train','validation','test'):continue
        cl=(row.get('usable_class') if kind=='bmp' else row.get('presence_class'))
        if cl not in ('positive','negative'):continue
        if row.get('spectrogram_eligible' if kind=='bmp' else 'wav_eligible')!='true':continue
        # Only human-reviewed evidence. Never turn Don't Know into hard negative.
        if row.get('review_provenance') not in ('reviewed_metadata','reviewed_confirmed'):continue
        rel=row.get('original_bmp' if kind=='bmp' else 'original_wav')
        if not rel:continue
        original=allowed_path(root,rel)
        annotation=allowed_path(root,row['original_bmp']+'.data')
        if not original.is_file() or not annotation.is_file():
            invalid.append({'recording':rel,'reason':'missing_media_or_annotation'});continue
        if count_sha(annotation)!=row.get('annotation_sha256'):
            invalid.append({'recording':rel,'reason':'annotation_changed_since_audit'});continue
        try:orig_hash=count_sha(original)
        except OSError:
            invalid.append({'recording':rel,'reason':'unreadable_media'});continue
        if orig_hash in seen_sha:
            prior=seen_sha[orig_hash]
            duplicates.append({'recording':rel,'duplicate_of':prior['source'],'split':row['split'],'first_split':prior['split']})
            if row['split']!=prior['split']:
                raise RuntimeError('LEAKAGE: identical original media in multiple frozen splits: '+rel+' vs '+prior['source'])
            continue
        seen_sha[orig_hash]={'source':rel,'split':row['split']}
        try:weight=float(row.get('suggested_weight') or 1.0)
        except ValueError:weight=1.0
        chosen.append({'source':rel,'file_path':str(original),'source_sha256':orig_hash,
            'annotation_sha256':row['annotation_sha256'], 'recording':row['recording'],
            'night':row['night'],'recorder':row['recorder'],'split':row['split'],
            'label':1 if cl=='positive' else 0,
            'quality':row.get('quality',''), 'confidence_grade':row.get('confidence_grade',''),
            'weight':max(.01,min(1.,weight))})
    return chosen,duplicates,invalid


def choose_examples(rows:list[dict],max_neg_ratio:float=8.0,max_neg_per_night:int=120):
    """Sample only TRAINING negatives, retain ALL validation/test data."""
    trains=[r for r in rows if r['split']=='train']
    pos=sum(r['label']==1 for r in trains)
    train_negative=[r for r in trains if r['label']==0]
    if not pos:raise ValueError('No eligible training positives')
    buckets=defaultdict(list)
    for r in train_negative:buckets[r['night']].append(r)
    selected=[]
    for night,subset in sorted(buckets.items()):
        subset.sort(key=lambda r:hashlib.sha256((r['source']+'|'+str(SEED)).encode()).hexdigest())
        selected.extend(subset[:max_neg_per_night])
    selected.sort(key=lambda r:hashlib.sha256((r['source']+'|global').encode()).hexdigest())
    max_neg=max(pos,int(pos*max_neg_ratio))
    chosen={r['source'] for r in selected[:max_neg]}
    return [r for r in rows if r['split']!='train' or r['label']==1 or r['source'] in chosen]


def scores(y_true,prob,threshold):
    pred=(prob>=threshold).astype(int)
    tn,fp,fn,tp=confusion_matrix(y_true,pred,labels=[0,1]).ravel()
    def div(a,b):return round(float(a/b),4) if b else None
    return {'n':len(y_true),'positive':int(sum(y_true)), 'negative':int(len(y_true)-sum(y_true)),
        'tp':int(tp),'fp':int(fp),'tn':int(tn),'fn':int(fn),
        'recall':div(tp,tp+fn),'precision':div(tp,tp+fp),
        'false_positive_rate':div(fp,fp+tn),'specificity':div(tn,tn+fp)}


def choose_threshold(yval,probs,target=.95):
    pos=int(np.sum(yval==1));neg=int(np.sum(yval==0))
    if pos<2 or neg<2:
        return 0.5, 'not_tunable_validation_missing_class_or_too_few'
    # Threshold is tuned on validation only. Max threshold satisfying target
    # recall minimises the rejected background while aiming to retain bats.
    valid=[0.,.001,*sorted(set(float(x) for x in probs))]
    feasible=[t for t in valid if scores(yval,probs,t)['recall'] is not None and
              scores(yval,probs,t)['recall']>=target]
    if not feasible:return 0.0,'no_recall_target_feasible'
    return float(max(feasible)),'validation_recall_target'


def train_one(kind:str,root:Path,phase:Path,output_base:Path, max_ratio:float=8.,max_per_night:int=120):
    manifest=phase/('spectrogram_candidates.csv' if kind=='bmp' else 'wav_candidates.csv')
    if not manifest.is_file():raise FileNotFoundError('Run Training_Data_Audit first: '+str(manifest))
    rows,duplicates,invalid=sample_manifest(manifest,kind,root)
    rows=choose_examples(rows,max_ratio,max_per_night)
    ct={s:dict(Counter('positive' if r['label'] else 'negative' for r in rows if r['split']==s)) for s in ('train','validation','test')}
    if not ct['train'].get('positive') or not ct['train'].get('negative'):
        raise ValueError('Need training positives AND negatives after filtering: '+str(ct))
    extract=bmp_features if kind=='bmp' else wav_features
    features=[]; retained=[]; extraction_errors=[]
    for n,row in enumerate(rows,1):
        try:
            feat=extract(Path(row['file_path']))
            if feat.shape!=(165,) or not np.all(np.isfinite(feat)):
                raise ValueError('Invalid features '+str(feat.shape))
            features.append(feat);retained.append(row)
        except Exception as exc:
            extraction_errors.append({'source':row['source'],'error':str(exc)[:300]})
        if n%100==0:print(f'[{kind}] Extracted {n}/{len(rows)} source files',flush=True)
    if not retained:raise RuntimeError('No valid '+kind+' inputs')
    X=np.stack(features);ys=np.asarray([r['label'] for r in retained]);
    split=np.asarray([r['split'] for r in retained]);weights=np.asarray([r['weight'] for r in retained])
    train_mask=split=='train';valid_mask=split=='validation';test_mask=split=='test'
    if len(np.unique(ys[train_mask]))!=2:
        raise ValueError('Training set lost positive or negative class during feature extraction')
    model=make_pipeline(StandardScaler(),LogisticRegression(solver='liblinear',max_iter=800,
                          class_weight='balanced',random_state=SEED))
    print(f'[{kind}] Training balanced baseline on {sum(train_mask)} recording-level examples...',flush=True)
    model.fit(X[train_mask],ys[train_mask],logisticregression__sample_weight=weights[train_mask])
    probabilities=model.predict_proba(X)[:,1]
    threshold,status=choose_threshold(ys[valid_mask],probabilities[valid_mask])
    report={'schema':1,'model_family':kind,'algorithm':'balanced_logistic_regression_on_robust_time_frequency_features',
      'feature_version':FEATURE_VERSION,'seed':SEED, 'threshold':threshold,'threshold_source':status,
      'intended_purpose':'EXPERIMENTAL DESKTOP benchmark, NOT AviaNZ .h5, NOT ESP32 firmware',
      'created_utc':datetime.now(timezone.utc).isoformat(),
      'input_manifest':str(manifest),'input_manifest_sha256':count_sha(manifest),
      'night_splits_file':str(phase/'night_splits.json'),'night_splits_sha256':count_sha(phase/'night_splits.json'),
      'sample_counts':ct,'selected':len(retained),'duplicate_files_skipped':duplicates,
      'source_validation_failures':invalid,'feature_failures':extraction_errors,
      'sample_weight_note':'Legacy confirmed labels receive downweighted sample_weight; grades 1..5 are not probabilities.',
      'waveband_note':'WAV model uses only 8-45 kHz time-frequency content at 96 kHz analysis rate, including for 192 kHz source.',
      'recording_level_limitation':'Labels mark recording presence; not every frame in a positive recording is a bat call.',
      'metrics':{} }
    for name,mask in (('train',train_mask),('validation',valid_mask),('test',test_mask)):
        report['metrics'][name]=scores(ys[mask],probabilities[mask],threshold) if mask.any() else None
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'_'+count_sha(manifest)[:8]
    dest=output_base/kind/run_id
    dest.mkdir(parents=True,exist_ok=False)
    joblib.dump(model,dest/'baseline.joblib',compress=3)
    report['model_sha256']=count_sha(dest/'baseline.joblib')
    (dest/'model_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    with (dest/'predictions.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['night','recorder','recording','source','split','human_label','grade','quality','model_probability','model_prediction','source_sha256']
        wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader()
        for row,prob in zip(retained,probabilities):
            wr.writerow({'night':row['night'],'recorder':row['recorder'],'recording':row['recording'],
                'source':row['source'],'split':row['split'],'human_label':'bat' if row['label'] else 'noise',
                'grade':row['confidence_grade'],'quality':row['quality'],
                'model_probability':round(float(prob),6),'model_prediction':'bat' if prob>=threshold else 'noise',
                'source_sha256':row['source_sha256']})
    print(f'[{kind}] Model saved: {dest}',flush=True)
    print(f'[{kind}] Validation: {report["metrics"]["validation"]}',flush=True)
    print(f'[{kind}] Frozen TEST: {report["metrics"]["test"]}',flush=True)
    return dest,report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.home()/'Documents'/'Bat')
    p.add_argument('--phase',type=Path)
    p.add_argument('--family',choices=('both','bmp','wav'),default='both')
    p.add_argument('--max-negative-ratio',type=float,default=8.0)
    p.add_argument('--max-negative-per-night',type=int,default=120)
    a=p.parse_args()
    root=a.root.expanduser().resolve()
    phase=(a.phase or root/'Daily_Run_Reports'/'Training_Phase1').expanduser().resolve()
    out=root/'Daily_Run_Reports'/'Model_Experiments'
    if not (phase/'night_splits.json').is_file():raise ValueError('Run the Phase 1 audit first to freeze evaluation nights')
    families=MODELS if a.family=='both' else (a.family,)
    errors=[]
    for family in families:
        try:train_one(family,root,phase,out,a.max_negative_ratio,a.max_negative_per_night)
        except Exception as e:
            print(f'[{family}] FAILED: {e}',file=sys.stderr,flush=True)
            errors.append(family)
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
