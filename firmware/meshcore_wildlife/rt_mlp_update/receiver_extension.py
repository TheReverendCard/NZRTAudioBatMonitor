"""Extend the installed Bat receiver without replacing its SD/RT log handlers."""
import argparse,hashlib,hmac,importlib.util,json,re,struct,threading
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parent.parent

def load_receiver(path):
 spec=importlib.util.spec_from_file_location('bat_existing_receiver',path)
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 for attr in ['Handler','Server','publish','fnv']:
  if not hasattr(mod,attr):raise ValueError('Unsupported receiver API: '+attr)
 return mod

def extended_handler(base,models):
 class Handler(base.Handler):
  def authorized(self):
   return any(hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+t).encode()) for t in self.server.tokens)
  def do_GET(self):
   if not self.authorized():return self.reply(401,'Unauthorized')
   control=re.fullmatch('/rt-control/([0-9a-f]{12})',self.path)
   if control:
    folder=self.server.root/'RT_Controls';request=folder/(control[1]+'.json');ack=folder/(control[1]+'.ack.json')
    if not request.is_file():return self.reply(204,'')
    with self.server.commit_lock:
     entry=json.loads(request.read_text());previous=json.loads(ack.read_text()) if ack.exists() else {}
    if previous.get('id')==entry['id']:return self.reply(204,'')
    command=entry['command']
    if not re.fullmatch(r'(wav (on|off)|mode shadow|mode active ([0-9a-f]{64}|builtin-wav-mlp-v01)|model fetch [0-9a-f]{64})',command) or not re.fullmatch('[0-9a-f]{32}',entry['id']):return self.reply(422,'Invalid control')
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
     path=folder/(ack[1]+'.ack.json');tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({'id':ident,'accepted_utc':datetime.now(timezone.utc).isoformat(),'meaning':'command accepted; model downloads have separate journal results'}));tmp.replace(path)
    return self.reply(200,'OK')
   if self.path!='/rt-clip':return super().do_POST()
   self.connection.settimeout(15)
   if not self.authorized():return self.reply(401,'Unauthorized')
   name=self.headers.get('X-Name','');device=self.headers.get('X-Device','');expected=self.headers.get('X-FNV1a','')
   match=re.fullmatch(r'(\d{10})_([0-9a-f]{8})_(\d+)_(\d+)\.wav',name)
   if not match or not re.fullmatch('[0-9a-f]{12}',device) or not re.fullmatch('[0-9a-f]{8}',expected):return self.reply(400,'Invalid identity')
   try:n=int(self.headers.get('Content-Length','-1'));fs=int(self.headers.get('X-Sample-Rate','0'))
   except ValueError:return self.reply(400,'Invalid length/rate')
   if n<=0 or n>768000 or n%2 or fs!=192000:return self.reply(400,'Invalid length/rate')
   try:
    pcm=self.rfile.read(n)
    if len(pcm)!=n or base.fnv(pcm)!=expected:return self.reply(422,'Length/checksum mismatch')
    utc=int(match[1]);stamp=datetime.fromtimestamp(utc,timezone.utc)
    local=stamp.astimezone(ZoneInfo('Pacific/Auckland'))
    session,run,seq=match.groups()[1:];folder=self.server.root/'RT_Clips'/device/local.strftime('%Y%m%d');folder.mkdir(parents=True,exist_ok=True)
    # Local timestamp first, with session/run/sequence to prevent repeated-time collisions.
    path=folder/(local.strftime('%Y%m%d_%H%M%S')+f'_RT_{session}_{run}_{seq}.wav')
    content=struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',n+36,b'WAVE',b'fmt ',16,1,1,fs,fs*2,2,16,b'data',n)+pcm
    meta={'schema':'nzrt-mlp-clip-1','source_device':'Xiao RT','device_id':device,'session':session,'run':int(run),'seq':int(seq),'sample_rate':fs,'samples':n//2,'utc_start':utc,'timestamp_resolution_seconds':1,'local_start':local.isoformat(),'capture_valid':self.headers.get('X-Capture-Valid')=='1','model':self.headers.get('X-Model'),'firmware':self.headers.get('X-Firmware'),'pcm_sha256':hashlib.sha256(pcm).hexdigest(),'pcm_fnv1a':expected,'clip_policy':'pre250_post1750','label':'unreviewed'}
    with self.server.commit_lock:
     base.publish(path,content);base.publish(path.with_suffix('.json'),(json.dumps(meta,indent=2,sort_keys=True)+'\n').encode())
    return self.reply(200,'OK '+expected)
   except FileExistsError:return self.reply(409,'Conflicting clip')
   except (OSError,TimeoutError):return self.reply(500,'Storage or transfer failed')
 return Handler

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
 server.serve_forever()
if __name__=='__main__':
 try:main()
 except KeyboardInterrupt:pass
 except Exception as e:print('STOPPED:',e);raise SystemExit(1)
