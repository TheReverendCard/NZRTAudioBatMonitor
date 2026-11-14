"""Serial protocol simulations; no physical device or pyserial installation needed."""
import unittest
from collections import deque
from unittest.mock import patch
import rt_compare as run

class Board:
    def __init__(self, *, fault='', existing=False):
        self.q=deque();self.commands=[];self.session=None
        self.fault=fault;self.existing=existing
    def send(self, cmd):
        # Production code must drain stage END/ACK before issuing the next stage.
        if self.q and cmd!='nzrt compare stop': raise AssertionError((cmd,self.q))
        self.commands.append(cmd)
        if cmd=='nzrt status':self.q.append('NZRT DIAG build=NZRT-J4-GUARD-2 session=ABC12345')
        elif cmd=='nzrt test status':
            self.q.append('NZRT TEST_STATUS bench=0 period_s=%s buffer=1 state=idle'%('300' if self.existing else '0'))
        elif cmd=='nzrt compare prepare':self.q.append('NZRT TEST bench=ON duration_s=3600')
        elif cmd=='nzrt compare stop':
            self.q.clear();self.q.append('NZRT TEST bench=OFF periodic=OFF')
        else:
            s=cmd.split()[-1]
            if s=='score' and self.commands.count(cmd)==1:
                self.q.append('NZRT COMPARE WAIT previous_audio_or_network');return
            n=str(run.STAGES.index(s)+7)
            ack='NZRT TEST session=abc12345 run=0 seq='+n+' source=manual result=ACK'
            self.q.extend(['NZRT COMPARE START stage='+s,'NZRT TEST session=abc12345 run=0 seq='+n+' source=manual result=ARMED',
              'NZRT TEST_AUDIO seq='+n+' samples=384000 zero_filled=0 continuous=1','NZRT COMPARE TIMING stage='+s+' queue_peak=21'])
            if self.fault!='incomplete': self.q.append('NZRT COMPARE COUNTERS stage='+s+' drops=2 gaps=1')
            if s=='send':self.q.append(ack)
            self.q.append('NZRT COMPARE END stage='+s+' seq='+n+' elapsed_ms=20001')
            if s!='send':
                self.q.append('NZRT LIVE result=ACK')
                self.q.append(ack.replace('seq='+n,'seq=999') if self.fault=='wrong' else ack)
    def line(self,deadline):
        if not self.q:raise TimeoutError('no more serial data')
        return self.q.popleft()

class ProtocolTest(unittest.TestCase):
    def test_stages(self):
        b=Board();r={'stages':{}}
        with patch.object(run.time,'sleep'):run.execute(b,r)
        self.assertTrue(r['automatic_schedule_restored'] and r['measurements_complete'])
        self.assertEqual(b.commands.count('nzrt compare score'),2)
        self.assertTrue(all(x['receiver_ack'] and x['counters']['drops']=='2' for x in r['stages'].values()))
    def test_wrong_ack_and_missing_measurements(self):
        for fault in ['wrong','incomplete']:
            b=Board(fault=fault);r={'stages':{}}
            with self.assertRaises((TimeoutError,RuntimeError)):run.execute(b,r)
            self.assertTrue(r['automatic_schedule_restored'])
            self.assertNotIn('nzrt compare score',b.commands)
    def test_leave_existing_periodics(self):
        b=Board(existing=True)
        with self.assertRaises(RuntimeError):run.execute(b,{'stages':{}})
        self.assertEqual(b.commands,['nzrt status','nzrt test status'])

if __name__=='__main__':unittest.main()
