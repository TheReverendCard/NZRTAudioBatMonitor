from pathlib import Path
import importlib.util,unittest,tempfile,subprocess,struct,random,wave,json,threading
HERE=Path(__file__).resolve().parent
import os
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
receiver=module('staged_receiver',HERE.parent/'receiver/receiver_extension.py')
oldtests=module('existing_receiver_tests',HERE/'receiver_cases.py')
oldtests.extended_handler=receiver.extended_handler
def encode(pcm):
    with tempfile.TemporaryDirectory() as td:
        p=Path(td);(p/'in.pcm').write_bytes(pcm)
        subprocess.run([os.environ['RT_CODEC_PROBE'],str(p/'in.pcm'),str(p/'out.bin')],check=True)
        return (p/'out.bin').read_bytes()
class CodecTests(unittest.TestCase):
    def test_exact_cpp_python_roundtrips(self):
        rng=random.Random(1701);cases=[]
        for count in (1,255,256,257,4097,384000):
            for value in (-32768,0,32767):cases.append(struct.pack('<h',value)*count)
        for width in range(1,17):
            values=[rng.randrange(1<<width)-32768 for _ in range(10001)]
            cases.append(struct.pack('<'+str(len(values))+'h',*values))
        samples=[rng.randrange(-32768,32768) for _ in range(384000)];cases.append(struct.pack('<384000h',*samples))
        recordings=sorted(Path(os.environ['RT_CODEC_RECORDINGS']).rglob('*.wav'))[:8] if os.environ.get('RT_CODEC_RECORDINGS') else []
        for path in recordings:
            with wave.open(str(path),'rb') as w:cases.append(w.readframes(w.getnframes()))
        ratios=[]
        for pcm in cases:
            packed=encode(pcm);self.assertEqual(receiver.decode_rtpcm1(packed),pcm);ratios.append(len(packed)/len(pcm))
        self.assertGreaterEqual(len(cases),35)
    def test_malformed_bounds(self):
        good=encode(b'\0\0'*257)
        bad=[b'',b'NOPE'+good[4:],b'RTB1'+struct.pack('<I',0),b'RTB1'+struct.pack('<I',384001),good[:-1],good+b'\0',good[:10]+b'\x11'+good[11:]]
        # A valid block shape whose decoded value exceeds signed PCM16.
        bad.append(b'RTB1'+struct.pack('<IhBB',1,32767,1,1))
        # Nonzero padding is not a second representation of the same samples.
        bad.append(b'RTB1'+struct.pack('<IhBB',1,0,1,128))
        for data in bad:
            with self.assertRaises(ValueError):receiver.decode_rtpcm1(data)
class ReceiverTests(oldtests.ReceiverTests):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.base=receiver.load_receiver(HERE/'fixtures/receiver_base.py')
        self.models=self.root/'models';self.models.mkdir()
        self.server=self.base.Server(('127.0.0.1',0),self.root,['old-sd-token','new-rt-token'])
        self.server.RequestHandlerClass=receiver.extended_handler(self.base,self.models)
        self.thread=threading.Thread(target=receiver.serve_receiver,args=(self.server,),daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
    def test_lossless_routes_and_integrity(self):
        pcm=struct.pack('<1001h',*(i%101-50 for i in range(1001)));packed=encode(pcm);h=self.base.fnv(pcm)
        heads={'X-Name':'1793927456_1234abcd_1_3.wav','X-Device':'123456abcdef','X-FNV1a':h,'X-Sample-Rate':'192000','X-Capture-Valid':'1','X-PCM-Encoding':'rtpcm1','X-PCM-Bytes':str(len(pcm))}
        self.assertEqual(self.request('/rt-transport-version'),(200,b'RTPCM1'))
        self.assertEqual(self.request('/rt-transport-version',token='wrong')[0],401)
        self.assertEqual(self.request('/rt-clip',packed,heads),(200,('OK '+h).encode()))
        self.assertEqual(self.request('/rt-clip',packed,heads)[0],200)
        path=next((self.root/'RT_Clips').rglob('*.wav'));self.assertEqual(path.read_bytes()[44:],pcm)
        meta=json.loads(path.with_suffix('.json').read_text());self.assertEqual(meta['samples'],1001);self.assertEqual(meta['transport_encoding'],'rtpcm1')
        diagnostic={**heads,'X-Test-Source':'load_probe','X-Missing-Samples':'0'}
        self.assertEqual(self.request('/rt-test-clip',packed,diagnostic)[0],200)
        self.assertEqual(next((self.root/'RT_Test_Clips').rglob('*.wav')).read_bytes()[44:],pcm)
        bench={**heads,'X-Name':'1793927456_1234abcd_1_4.wav','X-Test-Source':'bench_candidate','X-First-Pass':'evolved','X-Pass-Policy':'assist'}
        self.assertEqual(self.request('/rt-clip',packed,bench)[0],200)
        self.assertEqual(self.request('/rt-clip',packed,{**heads,'X-PCM-Bytes':'2'})[0],422)
        self.assertEqual(self.request('/rt-clip',packed[:-1],heads)[0],422)
        self.assertEqual(self.request('/rt-clip',packed,{**heads,'X-FNV1a':'00000000'})[0],422)
        self.assertEqual(self.request('/rt-clip',packed,{**heads,'X-PCM-Encoding':'unknown'})[0],415)
if __name__=='__main__':unittest.main()
