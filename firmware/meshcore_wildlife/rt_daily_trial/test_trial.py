from pathlib import Path
import hashlib,json,sqlite3,tempfile,unittest
from unittest.mock import patch
from datetime import datetime,timezone
import rt_trial as t

class Trial(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.home=self.root/'reports'
        self.home.mkdir()

    def test_snapshot_dedup_and_shared(self):
        line='NZRT CANDIDATE session=0123ABCD run=1 seq={} clip_owner_seq=1 clip_request={} bench=0 first_pass=legacy pass_shadow=evolved pass_shadow_hit={} ended_reason=0\n'
        for n in ('a','b'):
            (self.root/(n+'.txt')).write_text(line.format(1,'armed',0)+line.format(2,'shared',1))
        db=sqlite3.connect(':memory:')
        records,_=t.observations(self.root,db)
        self.assertEqual(len(records['0123ABCD:1:1']),2)
        self.assertEqual(t.observations(self.root,db)[0],records)

    def test_pass_and_promotion(self):
        clips={}
        rows=['pass_id,night,reference,coverage,rt_event_id']
        for i in range(300):
            night='20261112' if i%2 else '20261113'
            key=f'ABCD0000:1:{i+1}'
            clips[key]=dict(night=night,grade=5,hit=1,replay={'audible':True})
            rows.append(f'pass-{i},{night},independent review,verified,{key}')
        clips['noise']=dict(night='20261113',grade=1,hit=0,replay={'audible':False})
        rows.append('outage,20261113,AR4,outage,')
        (self.home/'reviewed_passes.csv').write_text('\n'.join(rows))
        h=self.home/'health_comparison.csv'
        h.write_text('mode,seconds,dsp_gaps,dsp_drops,clips,incomplete\nlegacy,100,1,1,10,1\naudible,100,1,1,10,1\n')
        (self.home/'health_review.json').write_text(json.dumps(dict(device=t.DEVICE,firmware=t.BUILD,profile='audible',reviewer='tester',reviewed_noninferior=True,sha256=hashlib.sha256(h.read_bytes()).hexdigest())))
        r=t.assess(self.home,clips,'audible',{'first_night':'20261112'})
        self.assertEqual(r['reasons'],[])
        self.assertEqual(r['passes'],{'kept':300,'coverage_unknown_or_outage':1})
        self.assertIn('Known regression clip missed',t.assess(self.home,clips,'evolved',{'first_night':'20261112'})['reasons'])
        self.assertIn('status request',t.promote(self.home,self.root,r))
        folder=self.root/'RT_Controls';slot=folder/(t.DEVICE+'.json')
        ack=folder/(t.DEVICE+'.ack.json')
        def acknowledge(active,shadow):
            ack.write_text(json.dumps(dict(id=t.read(slot)['id'],accepted_utc=datetime.now(timezone.utc).isoformat(),first_pass=f'NZRT FIRST_PASS version=PASS-1 active={active} shadow={shadow} requested_active={active} requested_shadow={shadow}')))
        acknowledge('legacy','audible')
        self.assertIn('queued',t.promote(self.home,self.root,r))
        ident=t.read(slot)['id']
        self.assertEqual(t.read(slot)['command'],'pass audible legacy')
        self.assertIn('waiting',t.promote(self.home,self.root,r))
        self.assertEqual(t.read(slot)['id'],ident)
        acknowledge('audible','legacy')
        self.assertIn('applied',t.promote(self.home,self.root,r))
        ack.unlink()
        self.assertIn('historical',t.promote(self.home,self.root,r))
        rows.append('miss,20261113,AR4,verified,')
        (self.home/'reviewed_passes.csv').write_text('\n'.join(rows))
        self.assertTrue(t.assess(self.home,clips,'audible',{'first_night':'20261112'})['reasons'])

    def test_github_retry_and_same_day_edit(self):
        p=self.home/'outbox/day.md'
        t.atomic(p,'<!-- marker -->\nfirst')
        with patch.object(t,'gh',side_effect=OSError('offline')),self.assertRaises(OSError):t.sync(self.home)
        self.assertTrue(p.exists())
        previous=[[{'body':'<!-- marker -->\nprior','user':{'login':'owner'},'id':7}]]
        with patch.object(t,'gh',side_effect=['{"login":"owner"}',json.dumps(previous),'{}']) as runner:
            t.sync(self.home)
            self.assertIn('PATCH',runner.call_args.args)
        self.assertFalse(p.exists())
        self.assertTrue((self.home/'published/day.md').exists())

if __name__=='__main__':unittest.main()
