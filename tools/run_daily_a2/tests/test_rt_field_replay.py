import sys,tempfile,json,pathlib,shutil,wave,hashlib
from datetime import datetime,timezone
from pathlib import Path
import argparse
ap=argparse.ArgumentParser();ap.add_argument('tool',type=Path);ap.add_argument('capture_txt',type=Path);args=ap.parse_args()
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'payload'),str(args.tool.resolve())]
import daily_timeline as d, rt_logs as r,rt_audio_daily as audio
from PIL import Image
with tempfile.TemporaryDirectory() as t:
 root=Path(t); raw=root/'XiaoRT_Logs/Raw';raw.mkdir(parents=True);day='20261107'
 for p in (args.capture_txt,args.capture_txt.with_suffix('.json')):shutil.copy2(p,raw/p.name)
 parsed=r.load_archives(root);es=[e for e in parsed['events'] if e['session']=='5EB1281B'];assert sum(e['shadow_class']=='bat_like' for e in es)==234 and not parsed['ml']
 event=es[-1];t0=int(event['start']); stamp=datetime.fromtimestamp(t0,audio.NZ);session='5eb1281b';name=stamp.strftime('%Y%m%d_%H%M%S')+'_RT_'+session+'_2_400';device='bcd3d73f1fb8'
 wav=root/'WiFi_Backup/RT_Clips'/device/stamp.strftime('%Y%m%d')/(name+'.wav');wav.parent.mkdir(parents=True)
 pcm=b'\0\0'*384000
 with wave.open(str(wav),'wb') as w:w.setparams((1,2,192000,0,'NONE',''));w.writeframes(pcm)
 meta=dict(schema='nzrt-mlp-clip-1',source_device='Xiao RT',device_id=device,capture_valid=True,utc_start=t0,session=session,run=2,seq=400,samples=384000,sample_rate=192000,pcm_sha256=hashlib.sha256(pcm).hexdigest());wav.with_suffix('.json').write_text(json.dumps(meta))
 clips,errs=audio.prepare(root);assert not errs and day in clips
 bmp=clips[day][0];assert Image.open(bmp).size[0]==64
 Path(str(bmp)+'.data').write_text(json.dumps([{'Duration':2,'Reviewer':'Jesse Card - Untrained','Operator':'Auto','BatDailyReview':{'grade':5}}]))
 assert audio.prepare(root)[0]==clips
 line=f'NZRT ML session=5EB1281B run=2 seq=400 model=fixture feature_schema=1 mode=shadow probability=0.9 threshold=0.5 valid=1 decision=bat_candidate utc_start={t0}'
 log=raw/'fixture.txt';log.write_text(line+'\n'+line);log.with_suffix('.json').write_text(json.dumps(dict(complete=True,sha256=hashlib.sha256(log.read_bytes()).hexdigest())))
 d.refresh(root,{},[day]);obj=json.loads((root/'Daily_Timeline'/day/'timeline.json').read_text());m=obj['metadata'];print(m['rt_score_bat_like'],m['rt_shadow_ml_positives'],m['human_review_counts'])
 assert m['rt_shadow_ml_positives']==1 and m['human_review_counts']=={'confirmed':1}
 # Negative and invalid results never get positive marks.
 assert not r.parse_logs([('x',line.replace('valid=1','valid=0'))])['ml']
 assert not r.parse_logs([('x',line+'\n'+line.replace('0.9','0.8'))])['ml']
 wav.with_suffix('.json').write_text(json.dumps(dict(meta,pcm_sha256='bad')));assert audio.prepare(root)[1]
 print('PASS field replay; duplicate and conflicting ML; receiver PCM hash; RT BMP; grade 5; repeated import')
