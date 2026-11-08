import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'payload'))
import acoustic_pairs as ap
for residuals in ([10],[10,10],[10,10.5,11],[10,10,20,21]):
    rows=[dict(status='probable shared pass',ar4_utc=1000+i*1200,candidates=[dict(wav=str(i),residual_s=r)]) for i,r in enumerate(residuals)]
    groups=json.loads(json.dumps(ap.clock_groups(rows),allow_nan=False))
    assert all(type(g['usable']) is bool for g in groups)
    assert groups[0]['usable']==(len(residuals)>1)
print('PASS single-anchor, multi-anchor, drift and split clock groups serialize.')
