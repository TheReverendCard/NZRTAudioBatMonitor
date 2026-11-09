"""Private LAN PCM backup receiver. Python standard library only."""
import argparse, hashlib, hmac, json, os, re, secrets, socket, struct, tempfile, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def fnv(data):
    h=2166136261
    for b in data: h=((h^b)*16777619)&0xffffffff
    return f'{h:08x}'

def wav(pcm):
    return struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',len(pcm)+36,b'WAVE',b'fmt ',16,1,1,96000,192000,2,16,b'data',len(pcm))+pcm

def publish(path,data):
    # Serialize server commits. Never overwrite a different existing recording.
    if path.exists():
        if path.read_bytes()!=data: raise FileExistsError('Conflicting existing file')
        return
    fd,tmp=tempfile.mkstemp(prefix='.incoming_',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        # Exclusive creation via hardlink: works on NTFS and normal Linux filesystems.
        os.link(tmp,path)
        if path.read_bytes()!=data: raise OSError('Saved file readback mismatch')
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

class Handler(BaseHTTPRequestHandler):
    def reply(self,status,message):
        b=message.encode(); self.send_response(status);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_POST(self):
        self.connection.settimeout(15)
        if not any(hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+t).encode()) for t in self.server.tokens):
            return self.reply(401,'Unauthorized')
        if self.path not in ('/clip','/journal','/rt-log'): return self.reply(404,'Unknown route')
        name=self.headers.get('X-Name',''); expected=self.headers.get('X-FNV1a','')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,190}',name) or not re.fullmatch(r'[0-9a-f]{8}',expected):
            return self.reply(400,'Invalid name/hash')
        try: n=int(self.headers.get('Content-Length','-1'))
        except ValueError: return self.reply(400,'Invalid length')
        maximum=8*1024*1024 if self.path=='/rt-log' else (1920000 if self.path=='/clip' else 32768)
        if not 0<n<=maximum or (self.path=='/clip' and (n%2 or not name.endswith('.wav'))):
            return self.reply(400,'Invalid length/name')
        try:
            data=self.rfile.read(n)
            if len(data)!=n or fnv(data)!=expected: return self.reply(422,'Length/checksum mismatch')
            if self.path=='/rt-log':
                device=self.headers.get('X-Device','')
                try: stamp=int(self.headers.get('X-Snapshot-UTC','0'))
                except ValueError: return self.reply(400,'Invalid UTC')
                digest=hashlib.sha256(data).hexdigest()
                if (not re.fullmatch(r'[0-9a-f]{12}',device) or stamp<1760000000
                        or b'NZRT ' not in data or not data.endswith(b'\n')):
                    return self.reply(400,'Invalid RT snapshot')
                folder=self.server.root/'RT'/device
                folder.mkdir(parents=True,exist_ok=True)
                stem=f'{stamp}_{digest[:16]}'
                meta={'schema':'nzrt-wifi-log-1','complete':True,'device':device,
                      'snapshot_utc':stamp,'sha256':digest,'bytes':len(data),
                      'firmware':self.headers.get('X-Firmware','unknown')}
                with self.server.commit_lock:
                    publish(folder/(stem+'.txt'),data)
                    publish(folder/(stem+'.json'),(json.dumps(meta,sort_keys=True,indent=2)+'\n').encode())
                return self.reply(200,'OK '+expected)
            folder=self.server.root/('Clips' if self.path=='/clip' else 'Logs')
            if self.path=='/clip':
                match=re.fullmatch(r'([0-9a-f]{12})_((?:night|startup|sleep_check)_\d{8}T\d{6}Z_(?:\d{3}|[0-9a-f]{8}))_((?:event|periodic|startup)_\d{8}T\d{6}Z_\d{5}\.wav)',name)
                if match:
                    device,session,name=match.groups(); folder=folder/device/session
            folder.mkdir(parents=True,exist_ok=True)
            content=wav(data) if self.path=='/clip' else data
            with self.server.commit_lock:
                publish(folder/name,content)
                if self.path=='/clip':
                    # .json is a transport receipt, deliberately not AviaNZ .data.
                    meta={'schema':'sd104-wifi-receipt-1','pcm_fnv1a':expected,'pcm_sha256':hashlib.sha256(data).hexdigest(),'pcm_bytes':len(data),'sample_rate':96000,'capture_valid':self.headers.get('X-Capture-Valid')=='1','start_est_utc_us':self.headers.get('X-Start-UTC-Us','0'),'firmware':self.headers.get('X-Firmware','unknown'),'source':'RAM WiFi backup; not a species label'}
                    publish(folder/(name+'.json'),(json.dumps(meta,sort_keys=True,indent=2)+'\n').encode())
            self.reply(200,'OK '+expected)
        except FileExistsError: self.reply(409,'Conflicting existing file')
        except (OSError,TimeoutError): self.reply(500,'Storage or transfer failed')
    def log_message(self,fmt,*args): print(fmt%args,flush=True)

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,root,token):
        super().__init__(address,Handler);self.root=Path(root);self.tokens=[token] if isinstance(token,str) else list(token);self.commit_lock=threading.Lock()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8765);ap.add_argument('--root',default=str(Path.home()/'Documents'/'Bat'/'WiFi_Backup'));args=ap.parse_args()
    cfg=Path(__file__).with_name('receiver_config.json')
    if not cfg.exists(): cfg.write_text(json.dumps({'token':secrets.token_hex(24)},indent=2))
    config=json.loads(cfg.read_text())
    token=[config['token']]+config.get('additional_tokens',[])
    if not token or any(not isinstance(t,str) or not t.strip() for t in token):
        raise ValueError('Receiver tokens must be nonempty strings')
    print('Receiver folder:',args.root)
    print('Accepted tokens:',len(set(token)), '(values hidden)')
    print('Use this PC\'s LAN IPv4 from ipconfig in BACKUP_BASE_URL, e.g. http://192.168.1.50:8765')
    print('Private LAN only. Allow Python on Private networks if Windows prompts. Ctrl+C stops.')
    Server(('0.0.0.0',args.port),args.root,token).serve_forever()
if __name__=='__main__': main()
