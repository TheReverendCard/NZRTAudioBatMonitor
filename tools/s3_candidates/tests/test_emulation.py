import sys,tempfile,unittest,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from emulator_gate import parse
from training_guard import audio
from prediction_coverage import audit
from health_coverage import audit as health
from export_all import sha
class Gates(unittest.TestCase):
 def test_guest_results(self):
    tag='abc';ok='BAT_RESULT abc 0 0\nBAT_RESULT abc 1 1\nBAT_END abc\n'
    self.assertEqual(parse(ok,tag,[0,1],0)[0],[0,1])
    for bad in (ok.split('\n',1)[1],ok.replace('1 1','0 1'),ok.replace('1 1','1 nan'),ok.replace('BAT_END abc',''),ok.replace('1 1','2 1')):
        with self.subTest(data=bad),self.assertRaises(ValueError):parse(bad,tag,[0,1],0)
 def test_capture_receipt(self):
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'clip.wav'
        with wave.open(str(p),'wb') as f:f.setparams((1,2,96000,0,'NONE',''));f.writeframes(b'\0'*8192)
        self.assertEqual(audio(p)['samples'],4096)
        q=p.with_suffix('.wav.json');q.write_text('{"missing_samples":128}')
        with self.assertRaises(ValueError):audio(p)
        q.unlink();p.write_bytes(p.read_bytes()[:-20])
        with self.assertRaises(ValueError):audio(p)
 def test_prediction_coverage(self):
    with tempfile.TemporaryDirectory() as td:
        m=Path(td)/'m.csv';p=Path(td)/'predictions.csv'
        m.write_text('wav_eligible,split,confidence_grade,review_provenance,original_wav\ntrue,test,5,reviewed_metadata,a\ntrue,test,4,reviewed_metadata,b\n')
        p.write_text('source,split,grade,model_prediction,model_probability\na,test,5,noise,0.1\n');r=audit(m,sha(m),p,'wav')
        self.assertEqual(r['counts'],{'test:no_prediction':1,'test:reviewed_positive_below_threshold':1})
        self.assertEqual(audit(m,'bad',p,'wav')['status'],'snapshot_unavailable_or_changed')
 def test_health(self):
    line='NZRT FIELD health=1 session=A run=1 utc=1000 state=GAPS windows_delta=50 dsp_drop_delta=4 live_dropped=0'
    r=health([line,line,line.replace('1000','1200').replace('GAPS','MONITORING').replace('delta=4','delta=0')])
    self.assertEqual(r['totals'],dict(observed=1,reported_gap=1,reported_dsp_drop_delta_sum=4,separations_over_90s=1))
    self.assertIsNone(r['inferred_missed_calls'])
if __name__=='__main__':unittest.main()
