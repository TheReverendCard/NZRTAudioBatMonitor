import importlib.util,json,hashlib,struct,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from receiver_extension import load_receiver,extended_handler
from model_tool import validate
class ReceiverTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.base=load_receiver(Path(__file__).with_name('receiver_baseline.py'))
  self.models=self.root/'models';self.models.mkdir()
  self.server=self.base.Server(('127.0.0.1',0),self.root,['old-sd-token','new-rt-token']);self.server.RequestHandlerClass=extended_handler(self.base,self.models)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.url='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def request(self,route,data=None,headers=None,token='new-rt-token'):
  req=urllib.request.Request(self.url+route,data=data,headers={'Authorization':'Bearer '+token,**(headers or {})})
  try:
   with urllib.request.urlopen(req) as r:return r.status,r.read()
  except urllib.error.HTTPError as r:return r.code,r.read()
 def test_routes_and_pcm(self):
  pcm=struct.pack('<100h',*range(100));h=self.base.fnv(pcm)
  heads={'X-Name':'1793927456_1234abcd_1_2.wav','X-Device':'123456abcdef','X-FNV1a':h,'X-Sample-Rate':'192000','X-Capture-Valid':'1'}
  self.assertEqual(self.request('/rt-clip',pcm,heads),(200,('OK '+h).encode()))
  self.assertEqual(self.request('/rt-clip',pcm,heads)[0],200)
  wav=next((self.root/'RT_Clips').rglob('*.wav')).read_bytes();self.assertEqual(struct.unpack_from('<I',wav,24)[0],192000);self.assertEqual(wav[44:],pcm)
  self.assertEqual(self.request('/rt-clip',pcm,heads,token='wrong')[0],401)
  self.assertEqual(self.request('/rt-clip',pcm,{**heads,'X-Sample-Rate':'96000'})[0],400)
  self.assertEqual(self.request('/rt-clip',pcm,{**heads,'X-FNV1a':'00000000'})[0],422)
  self.assertEqual(self.request('/rt-clip',pcm,{**heads,'X-Name':'../escape.wav'})[0],400)
  # Existing SD endpoint and old token still operate at the original 96kHz.
  self.assertEqual(self.request('/clip',pcm,{'X-Name':'test.wav','X-FNV1a':h},token='old-sd-token')[0],200)
  self.assertEqual(struct.unpack_from('<I',(self.root/'Clips/test.wav').read_bytes(),24)[0],96000)
  log=b'NZRT SESSION id=123\n';lh=self.base.fnv(log)
  self.assertEqual(self.request('/rt-log',log,{'X-Name':'123456abcdef.txt','X-Device':'123456abcdef','X-FNV1a':lh,'X-Snapshot-UTC':'1793927456'})[0],200)
 def test_controls(self):
  device='123456abcdef';folder=self.root/'RT_Controls';folder.mkdir()
  route='/rt-control/'+device
  self.assertEqual(self.request(route)[0],204)
  ident='a'*32;path=folder/(device+'.json');path.write_text(json.dumps({'id':ident,'command':'wav on'}))
  self.assertEqual(self.request(route),(200,(ident+'\n'+'wav on').encode()))
  self.assertEqual(self.request(route,token='wrong')[0],401)
  self.assertEqual(self.request('/rt-control-ack/'+device,ident.encode())[0],200)
  self.assertEqual(self.request(route)[0],204)
  path.write_text(json.dumps({'id':'b'*32,'command':'erase'}));self.assertEqual(self.request(route)[0],422)
 def test_models(self):
  data=(Path(__file__).parents[1]/'models/wav_mlp_v01.bin').read_bytes();h=validate(data);(self.models/(h+'.bin')).write_bytes(data)
  self.assertEqual(self.request('/rt-model/'+h),(200,data))
  self.assertEqual(self.request('/rt-model/'+h,token='wrong')[0],401)
  self.assertEqual(self.request('/rt-model/'+'0'*64)[0],404)
  (self.models/(h+'.bin')).write_bytes(data[:-1]);self.assertEqual(self.request('/rt-model/'+h)[0],422)
  with self.assertRaises(ValueError):validate(data[:-1])
if __name__=='__main__':unittest.main()
