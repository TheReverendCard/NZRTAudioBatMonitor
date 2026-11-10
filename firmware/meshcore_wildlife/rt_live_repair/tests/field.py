"""Check that a quiet interval, a lost block, or a mismatched receipt cannot pass."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from field_check import check

event='NZRT CANDIDATE session=01 run=2 seq=9 class=uncertain'
trace=['NZRT DIAG build=NZRT-J4-LIVE-1', event, 'NZRT CANDIDATE_SAVED session=01 run=2 seq=9']
for n in [1,2]:
    trace += [f'NZRT MIC session=01 mode=MONITORING t={n*60}s bps=384000 dsp_done={n*100} dsp_gap=0 dsp_drop=0 errors=0 legacy_rx_q_ovf=0',
              f'NZRT BAND session=01 windows={n*3000}']
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    folder=root/'RT'/'device'
    folder.mkdir(parents=True)
    data=(event+'\n').encode()
    (folder/'e.txt').write_bytes(data)
    meta=folder/'e.json'
    def receipt(digest):
        meta.write_text(json.dumps(dict(complete=True,firmware='NZRT-J4-LIVE-1',sha256=digest)))
    receipt(hashlib.sha256(data).hexdigest())
    assert check(trace,root,0)
    assert not check([s for s in trace if not s.startswith('NZRT CANDIDATE_SAVED ')],root,0)
    assert not check([s for s in trace if not s.startswith('NZRT CANDIDATE ')],root,0)
    assert not check([s.replace('dsp_gap=0','dsp_gap=1') if 'dsp_done=200' in s else s for s in trace],root,0)
    receipt('bad')
    assert not check(trace,root,0)
print('PASS: hardware acceptance criteria')
