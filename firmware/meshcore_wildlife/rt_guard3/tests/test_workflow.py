import io,json,sys,tempfile,threading,types,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'optional_receiver'))
from prepare_build import stage
from modify import BASE
import run_loaded_test as run
from receiver_extension import extended_handler
class FakeLink:
 def __init__(self,fail=False):self.lines=[];self.commands=[];self.session=None;self.active=False;self.phase='load00';self.probes=0;self.infer=1;self.wav=1;self.fail=fail
 def send(self,c):
  self.commands.append(c)
  if c=='nzrt status':self.lines.append('NZRT DIAG build=NZRT-J5-GUARD-3 session=abcd')
  elif c=='nzrt load status':self.lines.append(f'NZRT WORK inference={self.infer} wav={self.wav} mode=shadow load={int(self.active)} bench={int(self.active)} period_s=0 idle=1 probes={self.probes} probe_busy=0')
  elif c=='nzrt health status':self.lines.append('NZRT JOURNAL_RAM errors=0 circuit=0')
  elif c=='nzrt load start':self.active=True;self.lines.append('NZRT LOAD started=1 real_scoring=1')
  elif c.startswith('nzrt load phase '):
   self.infer,self.wav=map(int,c.split()[-2:]);self.phase=f'load{self.infer}{self.wav}';self.lines.append('NZRT LOAD phase='+self.phase)
  elif c=='nzrt load finish':
   if not self.fail:self.lines.append(f'NZRT COMPARE COUNTERS stage={self.phase} blocks=1000 done=999 drops=0 gaps=0 dma_ovf=0 read_errors=0 short_reads=0')
   self.lines.append('NZRT LOAD finished=1')
  elif c=='nzrt load stop':self.active=False;self.infer=self.wav=1;self.lines.append('NZRT LOAD stopped=1 settings_restored=1')
 def line(self,deadline):
  if not self.lines:raise TimeoutError('test response absent')
  return self.lines.pop(0)
def fake_collect(link,seconds,rec):
 for _ in range(3):
  link.probes+=1;seq=str(link.probes)
  run.record(f'NZRT LOAD_ML seq={seq} valid={link.infer} score_reason={"complete" if link.infer else "disabled"} inference_us=1000',rec)
  if link.wav:run.record(f'NZRT LOAD_WAV seq={seq} result=ACK',rec)
class Tests(unittest.TestCase):
 def test_four_phases_and_missing_counters(self):
  for fail in (False,True):
   l=FakeLink(fail);r={'phases':{}}
   with patch.object(run,'collect',fake_collect):run.execute(l,r,300)
   self.assertTrue(r['settings_restored']);self.assertEqual(r['qualification_pass'],not fail);self.assertEqual(len(r['phases']),4)
 def test_cancel_restores(self):
  l=FakeLink();r={'phases':{}}
  with patch.object(run,'collect',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):run.execute(l,r,300)
  self.assertTrue(r['settings_restored']);self.assertFalse(l.active)
 def test_existing_bench_untouched(self):
  l=FakeLink();l.active=True
  with self.assertRaises(RuntimeError):run.execute(l,{'phases':{}},300)
  self.assertNotIn('nzrt load stop',l.commands)
 def test_stage_backup_and_unknown_rejection(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);src=root/'current';(src/'nzrt').mkdir(parents=True)
   (src/'platformio.ini').write_text('[env:test]\n')
   for n in BASE:(src/'nzrt'/n).write_bytes((ROOT/'base'/n).read_bytes())
   r=stage(src,root/'candidate')
   with zipfile.ZipFile(r['backup']) as z:self.assertEqual(z.read('nzrt/RTFeatures.h'),(src/'nzrt/RTFeatures.h').read_bytes())
   self.assertIn('NZRT-J5-GUARD-3',(root/'candidate/nzrt/WildlifeML.cpp').read_text())
   (src/'nzrt/RTFeatures.h').write_text('changed')
   with self.assertRaises(ValueError):stage(src,root/'reject')
   self.assertFalse((root/'reject').exists())
 def test_receiver_controls_and_ack(self):
  class Base:
   def reply(self,status,body):self.answer=status,body
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);folder=root/'RT_Controls';folder.mkdir();cls=extended_handler(types.SimpleNamespace(Handler=Base),root)
   h=object.__new__(cls);h.server=types.SimpleNamespace(root=root,tokens=['test-token'],commit_lock=threading.Lock());h.path='/rt-control/0123456789ab';h.headers={}
   h.do_GET();self.assertEqual(h.answer[0],401)
   h.headers={'Authorization':'Bearer test-token'}
   for cmd,code in [('infer off',200),('infer on',200),('health status',200),('pass assist evolved off',200),('infer erase',422)]:
    (folder/'0123456789ab.json').write_text(json.dumps({'id':'1'*32,'command':cmd}));h.do_GET();self.assertEqual(h.answer[0],code)
   h.path='/rt-control-ack/0123456789ab';h.headers.update({'Content-Length':'32','X-NZRT-Work':'NZRT WORK inference=0 wav=1','X-NZRT-Journal':'NZRT JOURNAL_RAM circuit=1'})
   h.rfile=io.BytesIO(b'1'*32);h.connection=types.SimpleNamespace(settimeout=lambda x:None);h.do_POST()
   ack=json.loads((folder/'0123456789ab.ack.json').read_text());self.assertIn('inference=0',ack['work']);self.assertIn('circuit=1',ack['journal'])
if __name__=='__main__':unittest.main()
