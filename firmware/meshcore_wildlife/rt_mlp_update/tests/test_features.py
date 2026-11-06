import sys,json,subprocess,tempfile,time,warnings
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly,chirp
sys.path.insert(0,str(Path(__file__).parent))
from reference_wav_features import wav_features
HERE=Path(__file__).resolve().parent
rng=np.random.default_rng(17);cases=[]
for duration in [.12,.5,2.]:
 t=np.arange(int(192000*duration))/192000
 for name,y in [('silence',t*0),('noise',rng.normal(0,.03,len(t))),('sweep',chirp(t,45000,duration,24000)*np.exp(-((t-duration/2)/.015)**2)+rng.normal(0,.001,len(t)))]:cases.append((f'{name}_{duration}',y))
for path in sorted(Path('upload').glob('*.wav')):
 try:
  with warnings.catch_warnings():
   warnings.simplefilter("error");fs,x=wavfile.read(path)
  if x.ndim!=1 or x.dtype!=np.int16 or fs not in (96000,192000) or len(x)<fs*.12:continue
  x=x[:fs*2].astype(np.float32)/32768
  if fs==96000:x=resample_poly(x,2,1)
  cases.append(('field_'+path.name,x))
 except Exception:pass
 if sum(n.startswith('field_') for n,_ in cases)>=8:break
results=[]
with tempfile.TemporaryDirectory() as d:
 for name,y in cases:
  pcm=(np.clip(y,-1,32767/32768)*32768).round().astype(np.int16)
  p=Path(d)/'a.wav';wavfile.write(p,192000,pcm);raw=Path(d)/'a.raw';pcm.tofile(raw)
  started=time.perf_counter();vals=np.fromstring(subprocess.check_output([str(HERE/'features_cli'),str(raw)],text=True),sep=' ')
  ref=wav_features(p);err=float(np.max(np.abs(vals[:165]-ref)))
  refprob=float(subprocess.check_output([str(HERE/'reference_scorer')],input=','.join(map(str,ref))+'\n',text=True))
  perr=abs(refprob-float(vals[165]))
  results.append({'case':name,'max_feature_error':err,'probability':float(vals[165]),'reference_probability':refprob,'probability_error':perr,'host_elapsed_seconds':time.perf_counter()-started})
  assert err<.006 and perr<.005,(name,err,perr)
print(json.dumps({'cases':results,'max_error':max(r['max_feature_error'] for r in results),'note':'96kHz field files resampled to 192kHz as parity fixtures, not evidence of microphone fidelity or MCU timing'},indent=2))
