"""Offline coverage experiment. WAV paths are explicit; no credentials or radio required."""
import argparse,csv,hashlib,json,subprocess,tempfile,wave
from pathlib import Path
from test_gate import prepare,HERE
def load(path):
 import numpy as np
 from scipy.signal import resample_poly
 with wave.open(str(path)) as f:
  n=f.getnframes();r=f.getframerate()
  if (f.getnchannels(),f.getsampwidth(),r) not in ((1,2,96000),(1,2,192000)):raise ValueError('requires mono PCM16 at 96 or 192 kHz')
  raw=f.readframes(n)
  if len(raw)!=2*n or n<r//2:raise ValueError('incomplete or too short')
  x=np.frombuffer(raw,'<i2').astype('float32')/32768
 return resample_poly(x,2,1).astype('<f4') if r==96000 else x.astype('<f4')
def run(files,bg,cxx,labels):
 import numpy as np
 profiles={'legacy':0,'evolved':1,'audible':2,'legacy_plus_evolved':17,'legacy_plus_audible':18}
 rows=[];bad=[]
 with tempfile.TemporaryDirectory() as t:
  d=Path(t);prepare(d);exe=d/'replay'
  subprocess.run([cxx,'-DNZRT_HOST_TEST','-std=c++11','-O2','-I'+str(HERE/'test/host'),'-I'+str(d),str(d/'WildlifeDetector.cpp'),str(HERE/'test/replay.cpp'),'-o',str(exe)],check=True)
  ref=load(bg) if bg else None
  for path in files:
   try:x=load(path)
   except (wave.Error,ValueError,EOFError,OSError) as e:bad.append({'clip':path.name,'reason':str(e)});continue
   # 4 s fixed pre-roll. With no reference, the clip's first 250 ms is held
   # out of the scored section and repeated (may contain a call).
   pre=np.resize(ref if ref is not None else x[:48000],768000)
   test=x if ref is not None else x[48000:]
   data=np.concatenate([pre,test]).astype('<f4').tobytes()
   sha=hashlib.sha256(path.read_bytes()).hexdigest()
   row={'clip':path.name,'wav_sha256':sha,'grade':labels.get(sha),'events':{}}
   for name,cfg in profiles.items():
    o=subprocess.run([str(exe),str(cfg)],input=data,stdout=subprocess.PIPE,check=True).stdout.decode()
    row['events'][name]=[{'start_ms':a-4000+(0 if ref is not None else 250),'end_ms':b-4000+(0 if ref is not None else 250),'mask':m}
      for l in o.splitlines() for a,b,m in [map(int,l.split(','))] if b>4000 and a<4000+len(test)*1000/192000]
   rows.append(row)
 return {'scope':'Decoded PCM; unlimited compute, per-file calibration, no real-time or species accuracy guarantee. File hits are not localised pulse matches.','preroll':'first 4 s of reference (repeat if shorter)' if bg else 'own first 250 ms repeated for 4 s; first 250 ms excluded from scored segment','reference_sha256':hashlib.sha256(bg.read_bytes()).hexdigest() if bg else None,'clips':rows,'rejected':bad}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--background',type=Path);p.add_argument('--labels',type=Path,help='CSV: source_sha256,grade');p.add_argument('--cxx',default='c++');v=p.parse_args()
 with v.output.open('x',encoding='utf8') as f:
  labels={}
  if v.labels:
   with v.labels.open(encoding='utf-8-sig') as table:
    labels={r['source_sha256']:r['grade'] for r in csv.DictReader(table)}
  json.dump(run(sorted(v.folder.rglob('*.wav')),v.background,v.cxx,labels),f,indent=2);f.write('\n')
