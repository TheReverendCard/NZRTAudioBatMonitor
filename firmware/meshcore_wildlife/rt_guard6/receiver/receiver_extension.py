"""Extend the installed Bat receiver without replacing its SD/RT log handlers."""
import argparse,hashlib,hmac,importlib.util,json,re,struct,threading
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import os
from http.server import ThreadingHTTPServer
ROOT=Path(os.environ.get('NZRT_BAT_ROOT',Path.home()/'Documents'/'Bat'))

def decode_rtpcm1(payload):
    """Decode bounded RTPCM1 blocks to exact little-endian PCM16 bytes."""
    import struct
    if len(payload)<8 or payload[:4]!=b'RTB1':raise ValueError('Invalid packed PCM header')
    samples=struct.unpack_from('<I',payload,4)[0]
    if not 1<=samples<=384000:raise ValueError('Invalid packed PCM sample count')
    pcm=bytearray(samples*2);pos=8
    for at in range(0,samples,256):
        count=min(256,samples-at)
        if pos+3>len(payload):raise ValueError('Truncated packed PCM block')
        minimum,width=struct.unpack_from('<hB',payload,pos);pos+=3
        if width>16:raise ValueError('Invalid packed PCM width')
        size=(count*width+7)//8
        if pos+size>len(payload):raise ValueError('Truncated packed PCM samples')
        packed=int.from_bytes(payload[pos:pos+size],'little');pos+=size;mask=(1<<width)-1
        for i in range(count):
            value=minimum+(packed&mask);packed>>=width
            if value>32767:raise ValueError('Packed PCM sample overflow')
            struct.pack_into('<h',pcm,2*(at+i),value)
        if packed:raise ValueError('Invalid packed PCM padding')
    if pos!=len(payload):raise ValueError('Trailing packed PCM bytes')
    return bytes(pcm)


def load_receiver(path):
 spec=importlib.util.spec_from_file_location('bat_existing_receiver',path)
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 for attr in ['Handler','Server','publish','fnv']:
  if not hasattr(mod,attr):raise ValueError('Unsupported receiver API: '+attr)
 return mod

def extended_handler(base,models):
 class Handler(base.Handler):
  def reply(self,status,text):
   if status>=400:
    print(json.dumps({'receiver_reject':status,'route':self.path,'reason':text,'name':self.headers.get('X-Name'),'encoding':self.headers.get('X-PCM-Encoding'),'pcm_bytes':self.headers.get('X-PCM-Bytes'),'body_bytes':self.headers.get('Content-Length')}),flush=True)
   return super().reply(status,text)
  def authorized(self):
   return any(hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+t).encode()) for t in self.server.tokens)
  def do_GET(self):
   if self.path=="/rt-transport-version" and self.authorized():return self.reply(200,"RTPCM1")
   if self.path=="/guard3-version" and self.authorized():return self.reply(200,"GUARD-3")
   if self.path=="/pass1-version" and self.authorized():return self.reply(200,"PASS-1")
   if not self.authorized():return self.reply(401,'Unauthorized')
   control=re.fullmatch('/rt-control/([0-9a-f]{12})',self.path)
   if control:
    folder=self.server.root/'RT_Controls';request=folder/(control[1]+'.json');ack=folder/(control[1]+'.ack.json')
    if not request.is_file():return self.reply(204,'')
    with self.server.commit_lock:
     entry=json.loads(request.read_text());previous=json.loads(ack.read_text()) if ack.exists() else {}
    if previous.get('id')==entry['id']:return self.reply(204,'')
    command=entry['command']
    if not re.fullmatch(r'(infer (on|off)|health status|pass (status|(legacy|evolved|audible) (off|legacy|evolved|audible)|assist (evolved|audible) (off|legacy|evolved|audible))|wav (on|off)|mode shadow|mode active ([0-9a-f]{64}|builtin-wav-mlp-v01)|model fetch [0-9a-f]{64}|record now|test (on|off)|scan (off|every [0-9]{1,5}))',command) or not re.fullmatch('[0-9a-f]{32}',entry['id']):return self.reply(422,'Invalid control')
    return self.reply(200,entry['id']+'\n'+command)
   match=re.fullmatch('/rt-model/([0-9a-f]{64})',self.path)
   if not match:return self.reply(404,'Unknown route')
   path=models/(match[1]+'.bin')
   if not path.is_file():return self.reply(404,'Model not staged')
   data=path.read_bytes()
   if len(data)!=24772 or hashlib.sha256(data).hexdigest()!=match[1]:return self.reply(422,'Invalid model')
   self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Content-Type','application/octet-stream');self.end_headers();self.wfile.write(data)
  def do_POST(self):
   ack=re.fullmatch('/rt-control-ack/([0-9a-f]{12})',self.path)
   if ack:
    if not self.authorized():return self.reply(401,'Unauthorized')
    self.connection.settimeout(5)
    if self.headers.get('Content-Length')!='32':return self.reply(400,'Invalid ack')
    ident=self.rfile.read(32).decode('ascii',errors='replace')
    if not re.fullmatch('[0-9a-f]{32}',ident):return self.reply(400,'Invalid ack')
    folder=self.server.root/'RT_Controls';folder.mkdir(parents=True,exist_ok=True)
    with self.server.commit_lock:
     path=folder/(ack[1]+'.ack.json');tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({'id':ident,'first_pass':self.headers.get('X-NZRT-Pass'),'work':self.headers.get('X-NZRT-Work'),'journal':self.headers.get('X-NZRT-Journal'),'accepted_utc':datetime.now(timezone.utc).isoformat(),'meaning':'command accepted; model downloads have separate journal results'}));tmp.replace(path)
    return self.reply(200,'OK')
   bench_candidate=self.path=='/rt-clip' and self.headers.get('X-Test-Source')=='bench_candidate'
   diagnostic=self.path=='/rt-test-clip'
   if not diagnostic and self.path!='/rt-clip':return super().do_POST()
   self.connection.settimeout(15)
   if not self.authorized():return self.reply(401,'Unauthorized')
   name=self.headers.get('X-Name','');device=self.headers.get('X-Device','');expected=self.headers.get('X-FNV1a','')
   match=re.fullmatch(r'(\d{10})_([0-9a-f]{8})_(\d+)_(\d+)\.wav',name)
   if not match or not re.fullmatch('[0-9a-f]{12}',device) or not re.fullmatch('[0-9a-f]{8}',expected):return self.reply(400,'Invalid identity')
   try:n=int(self.headers.get('Content-Length','-1'));fs=int(self.headers.get('X-Sample-Rate','0'))
   except ValueError:return self.reply(400,'Invalid length/rate')
   encoding=self.headers.get('X-PCM-Encoding','raw')
   if encoding not in ('raw','rtpcm1'):return self.reply(415,'Unsupported PCM encoding')
   if n<=0 or n>768000 or (encoding=='raw' and n%2) or fs!=192000:return self.reply(400,'Invalid length/rate')
   if diagnostic:
    source=self.headers.get('X-Test-Source','')
    missing=self.headers.get('X-Missing-Samples','')
    if source not in ('manual','periodic','load_probe') or not re.fullmatch(r'[0-9]{1,6}',missing) or int(missing)>384000:
     return self.reply(400,'Invalid diagnostic metadata')
   try:
    payload=self.rfile.read(n)
    if len(payload)!=n:return self.reply(422,'Length/checksum mismatch')
    try:pcm=decode_rtpcm1(payload) if encoding=='rtpcm1' else payload
    except ValueError:return self.reply(422,'Invalid packed PCM')
    if encoding=='rtpcm1' and self.headers.get('X-PCM-Bytes')!=str(len(pcm)):return self.reply(422,'Decoded length mismatch')
    if base.fnv(pcm)!=expected:return self.reply(422,'Length/checksum mismatch')
    transport_bytes=n;n=len(pcm)
    if diagnostic and int(missing)>n//2:return self.reply(400,'Invalid missing sample count')
    utc=int(match[1]);stamp=datetime.fromtimestamp(utc,timezone.utc)
    local=stamp.astimezone(ZoneInfo('Pacific/Auckland'))
    session,run,seq=match.groups()[1:];folder=self.server.root/('RT_Test_Clips' if diagnostic or bench_candidate else 'RT_Clips')/device/local.strftime('%Y%m%d');folder.mkdir(parents=True,exist_ok=True)
    # Local timestamp first, with session/run/sequence to prevent repeated-time collisions.
    path=folder/(local.strftime('%Y%m%d_%H%M%S')+f'_RT_{session}_{run}_{seq}.wav')
    content=struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',n+36,b'WAVE',b'fmt ',16,1,1,fs,fs*2,2,16,b'data',n)+pcm
    meta={'schema':'nzrt-mlp-clip-1','source_device':'Xiao RT','device_id':device,'session':session,'run':int(run),'seq':int(seq),'sample_rate':fs,'samples':n//2,'utc_start':utc,'timestamp_resolution_seconds':1,'local_start':local.isoformat(),'capture_valid':self.headers.get('X-Capture-Valid')=='1','model':self.headers.get('X-Model'),'firmware':self.headers.get('X-Firmware'),'pcm_sha256':hashlib.sha256(pcm).hexdigest(),'pcm_fnv1a':expected,'clip_policy':'pre250_post1750','label':'unreviewed'}
    meta.update(transport_encoding=encoding,transport_bytes=transport_bytes)
    if self.headers.get('X-First-Pass'):meta['first_pass']=self.headers['X-First-Pass']
    if bench_candidate:
     meta.update(label='equipment_test',test_source='bench_candidate')
    if diagnostic:
     meta.update(schema='nzrt-test-clip-1',label='equipment_test',clip_policy='pre250_post1750' if source=='load_probe' else 'forward_2s',test_source=source,zero_filled_samples=int(missing))
    with self.server.commit_lock:
     base.publish(path,content);base.publish(path.with_suffix('.json'),(json.dumps(meta,indent=2,sort_keys=True)+'\n').encode())
    print(f'SAVED {path} samples={n//2} continuous={meta["capture_valid"]}',flush=True)
    return self.reply(200,'OK '+expected)
   except FileExistsError:return self.reply(409,'Conflicting clip')
   except (OSError,TimeoutError):return self.reply(500,'Storage or transfer failed')
 return Handler

def serve_receiver(server):
 # This extension supplies the complete RT/control routes. The installed
 # base receiver also monkey-patches Server.serve_forever with an older
 # PASS-1 handler that would intercept X-First-Pass uploads before decoding.
 # Keep its SD/log handlers, but run the standard server loop exactly once.
 return ThreadingHTTPServer.serve_forever(server)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--receiver',type=Path);ap.add_argument('--port',type=int,default=8765);ap.add_argument('--root',type=Path);args=ap.parse_args()
 cfgpath=ROOT/'bat_config.json';cfg=json.loads(cfgpath.read_text(encoding='utf-8-sig')) if cfgpath.exists() else {}
 args.root=args.root or Path(cfg.get('receiver',{}).get('backup_root',str(ROOT/'WiFi_Backup')))
 saved=cfg.get('receiver',{}).get('script');path=args.receiver or (Path(saved) if saved else None)
 if not path or not path.is_file():
  choices=[p for p in ROOT.glob('*/receiver.py') if 'backup' not in str(p.parent.name).lower()]
  for i,p in enumerate(choices,1):print(f'{i}: {p}')
  value=input('Select existing receiver number, or full receiver.py path: ').strip().strip('"')
  path=choices[int(value)-1] if value.isdigit() and 1<=int(value)<=len(choices) else Path(value)
  if not path.is_file():raise ValueError('Receiver file not found')
 base=load_receiver(path)
 configpath=path.with_name('receiver_config.json')
 existing=json.loads(configpath.read_text(encoding='utf-8-sig'));tokens=[existing['token']]+existing.get('additional_tokens',[])
 if not tokens or any(not isinstance(t,str) or not t for t in tokens):raise ValueError('Invalid receiver tokens')
 ZoneInfo('Pacific/Auckland') # fail before listening if tzdata is missing
 cfg.setdefault('receiver',{})['script']=str(path.resolve());cfg['receiver']['backup_root']=str(args.root);tmp=cfgpath.with_suffix('.tmp');tmp.write_text(json.dumps(cfg,indent=2)+'\n');tmp.replace(cfgpath)
 server=base.Server(('',args.port),args.root,tokens);server.RequestHandlerClass=extended_handler(base,ROOT/'Models'/'RT')
 print('Existing SD and RT log handlers retained. Accepted tokens:',len(set(tokens)))
 print('Xiao RT WAVs:',args.root/'RT_Clips');print('Models:',ROOT/'Models'/'RT')
 print('Private LAN only. Stop the old receiver before starting this one. Ctrl+C stops.')
 serve_receiver(server)
if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:pass
 except Exception as e:print('STOPPED:',e);raise SystemExit(1)
