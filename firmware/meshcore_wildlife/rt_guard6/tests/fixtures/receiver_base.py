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
# NZRT PASS-1 receiver integration v1
def _install_pass1_routes():
    import base64, hashlib, hmac, io, json, os, re, struct
    from datetime import datetime, timezone
    from pathlib import Path
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    def auckland():
        try:
            return ZoneInfo('Pacific/Auckland')
        except ZoneInfoNotFoundError:
            return ZoneInfo.from_file(io.BytesIO(base64.b64decode('VFppZjIAAAAAAAAAAAAAAAAAAAAAAAAAAAAABwAAAAAAAACcAAAABwAAABOAAAAAsLSy6LFRh1iyeOVos0PlYLRYx2i1I8dgtjipaLcDqWC4GItouOzF4Ln4bWi6zKfgu9hPaLzj6OC9rvbovsPK4L+O2OjAo6zgwW666MKDjuDDTpzoxGNw4MUufujGTI1gxw5g6Mgsb2DI931o0tqaQAkY/eAJrKXgCu+lYAue/OAM2MHgDX7e4A64o+APXsDgEJiF4BE+ouASeGfgEx6E4BRYSeAU/mbgFjgr4Bbng2AYIUhgGMdlYBoBKmAap0dgG+EMYByHKWAdwO5gHmcLYB+g0GAgRu1gIYCyYCIwCeAjac7gJA/r4CUuAWAmAkLgJw3jYCfiJOAo7cVgKcIG4CrNp2ArqyNgLK2JYC2LBWAujWtgL2rnYDBtTWAxSslgMlZp4DMqq2A0NkvgNQqNYDYWLeA286ngN/YP4DjTi+A51fHgOrNt4Du/DmA8k0/gPZ7wYD5zMeA/ftJgQFxOYEFetGBCPDBgQz6WYEQcEmBFHnhgRfv0YEb+WmBH94XgSN48YEnXZ+BKvh5gS7dJ4EyeAGBNlyvgTn3iYE93DeBQZv7gUWAqYFJG4OBTQAxgVCbC4FUf7mBWBqTgVv/QYFfmhuBY37JgWcZo4Fq/lGBbr4VgXKiw4F2PZ2BeiJLgX29JYGBodOBhTytgYkhW4GMvDWBkKDjgZQ7vYGYRVWBm+AvgZ/E3YGjX7eBp0RlgarfP4Guw+2Bsl7HgbZDdYG53k+BvcL9gcGCwYHFZ2+ByQJJgczm94HQgdGB1GZ/gdgBWYHb5geB34DhgeNlj4HnAGmB6uUXge6k24HyiYmB9iRjgfoJEYH9o+uACAQIDAgMCAwIDAgMCAwIDAgMCAwIDAgMCAwIDBgQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQAAKPYAAAAAK/IAQQAAKG4AAkAAKjAAQQAALbQAQ4AAKjAAAQAAKjAAARMTVQATlpTVABOWk1UAE5aRFQAAAAAAAEBAFRaaWYyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAcAAAAAAAAAnAAAAAcAAAAT/////0G3TKj/////sLSy6P////+xUYdY/////7J45Wj/////s0PlYP////+0WMdo/////7Ujx2D/////tjipaP////+3A6lg/////7gYi2j/////uOzF4P////+5+G1o/////7rMp+D/////u9hPaP////+84+jg/////72u9uj/////vsPK4P////+/jtjo/////8CjrOD/////wW666P/////Cg47g/////8NOnOj/////xGNw4P/////FLn7o/////8ZMjWD/////xw5g6P/////ILG9g/////8j3fWj/////0tqaQAAAAAAJGP3gAAAAAAmspeAAAAAACu+lYAAAAAALnvzgAAAAAAzYweAAAAAADX7e4AAAAAAOuKPgAAAAAA9ewOAAAAAAEJiF4AAAAAARPqLgAAAAABJ4Z+AAAAAAEx6E4AAAAAAUWEngAAAAABT+ZuAAAAAAFjgr4AAAAAAW54NgAAAAABghSGAAAAAAGMdlYAAAAAAaASpgAAAAABqnR2AAAAAAG+EMYAAAAAAchylgAAAAAB3A7mAAAAAAHmcLYAAAAAAfoNBgAAAAACBG7WAAAAAAIYCyYAAAAAAiMAngAAAAACNpzuAAAAAAJA/r4AAAAAAlLgFgAAAAACYCQuAAAAAAJw3jYAAAAAAn4iTgAAAAACjtxWAAAAAAKcIG4AAAAAAqzadgAAAAACurI2AAAAAALK2JYAAAAAAtiwVgAAAAAC6Na2AAAAAAL2rnYAAAAAAwbU1gAAAAADFKyWAAAAAAMlZp4AAAAAAzKqtgAAAAADQ2S+AAAAAANQqNYAAAAAA2Fi3gAAAAADbzqeAAAAAAN/YP4AAAAAA404vgAAAAADnV8eAAAAAAOrNt4AAAAAA7vw5gAAAAADyTT+AAAAAAPZ7wYAAAAAA+czHgAAAAAD9+0mAAAAAAQFxOYAAAAABBXrRgAAAAAEI8MGAAAAAAQz6WYAAAAABEHBJgAAAAAEUeeGAAAAAARfv0YAAAAABG/lpgAAAAAEf3heAAAAAASN48YAAAAABJ12fgAAAAAEq+HmAAAAAAS7dJ4AAAAABMngBgAAAAAE2XK+AAAAAATn3iYAAAAABPdw3gAAAAAFBm/uAAAAAAUWAqYAAAAABSRuDgAAAAAFNADGAAAAAAVCbC4AAAAABVH+5gAAAAAFYGpOAAAAAAVv/QYAAAAABX5obgAAAAAFjfsmAAAAAAWcZo4AAAAABav5RgAAAAAFuvhWAAAAAAXKiw4AAAAABdj2dgAAAAAF6IkuAAAAAAX29JYAAAAABgaHTgAAAAAGFPK2AAAAAAYkhW4AAAAABjLw1gAAAAAGQoOOAAAAAAZQ7vYAAAAABmEVVgAAAAAGb4C+AAAAAAZ/E3YAAAAABo1+3gAAAAAGnRGWAAAAAAarfP4AAAAABrsPtgAAAAAGyXseAAAAAAbZDdYAAAAABud5PgAAAAAG9wv2AAAAAAcGCwYAAAAABxWdvgAAAAAHJAkmAAAAAAczm94AAAAAB0IHRgAAAAAHUZn+AAAAAAdgBWYAAAAAB2+YHgAAAAAHfgOGAAAAAAeNlj4AAAAAB5wBpgAAAAAHq5ReAAAAAAe6k24AAAAAB8omJgAAAAAH2JGOAAAAAAfoJEYAAAAAB/aPrgAgECAwIDAgMCAwIDAgMCAwIDAgMCAwIDAgMCAwYEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEBQQFBAUEAACj2AAAAACvyAEEAAChuAAJAACowAEEAAC20AEOAACowAAEAACowAAETE1UAE5aU1QATlpNVABOWkRUAAAAAAABAQAKTlpTVC0xMk5aRFQsTTkuNS4wLE00LjEuMC8zCg==')), key='Pacific/Auckland')

    def extended_handler(base,models):
     class Handler(base.Handler):
      def authorized(self):
       return any(hmac.compare_digest(self.headers.get('Authorization','').encode(),('Bearer '+t).encode()) for t in self.server.tokens)
      def do_GET(self):
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
        if not re.fullmatch(r'(pass (status|(legacy|evolved|audible) (off|legacy|evolved|audible))|wav (on|off)|mode shadow|mode active ([0-9a-f]{64}|builtin-wav-mlp-v01)|model fetch [0-9a-f]{64}|record now|test (on|off)|scan (off|every [0-9]{1,5}))',command) or not re.fullmatch('[0-9a-f]{32}',entry['id']):return self.reply(422,'Invalid control')
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
         path=folder/(ack[1]+'.ack.json');tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({'id':ident,'first_pass':self.headers.get('X-NZRT-Pass'),'accepted_utc':datetime.now(timezone.utc).isoformat(),'meaning':'command accepted; model downloads have separate journal results'}));tmp.replace(path)
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
       if n<=0 or n>768000 or n%2 or fs!=192000:return self.reply(400,'Invalid length/rate')
       if diagnostic:
        source=self.headers.get('X-Test-Source','')
        missing=self.headers.get('X-Missing-Samples','')
        if source not in ('manual','periodic') or not re.fullmatch(r'[0-9]{1,6}',missing) or int(missing)>n//2:
         return self.reply(400,'Invalid diagnostic metadata')
       try:
        pcm=self.rfile.read(n)
        if len(pcm)!=n or base.fnv(pcm)!=expected:return self.reply(422,'Length/checksum mismatch')
        utc=int(match[1]);stamp=datetime.fromtimestamp(utc,timezone.utc)
        local=stamp.astimezone(auckland())
        session,run,seq=match.groups()[1:];folder=self.server.root/('RT_Test_Clips' if diagnostic or bench_candidate else 'RT_Clips')/device/local.strftime('%Y%m%d');folder.mkdir(parents=True,exist_ok=True)
        # Local timestamp first, with session/run/sequence to prevent repeated-time collisions.
        path=folder/(local.strftime('%Y%m%d_%H%M%S')+f'_RT_{session}_{run}_{seq}.wav')
        content=struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',n+36,b'WAVE',b'fmt ',16,1,1,fs,fs*2,2,16,b'data',n)+pcm
        meta={'schema':'nzrt-mlp-clip-1','source_device':'Xiao RT','device_id':device,'session':session,'run':int(run),'seq':int(seq),'sample_rate':fs,'samples':n//2,'utc_start':utc,'timestamp_resolution_seconds':1,'local_start':local.isoformat(),'capture_valid':self.headers.get('X-Capture-Valid')=='1','model':self.headers.get('X-Model'),'firmware':self.headers.get('X-Firmware'),'pcm_sha256':hashlib.sha256(pcm).hexdigest(),'pcm_fnv1a':expected,'clip_policy':'pre250_post1750','label':'unreviewed'}
        if self.headers.get('X-First-Pass'):meta['first_pass']=self.headers['X-First-Pass']
        if bench_candidate:
         meta.update(label='equipment_test',test_source='bench_candidate')
        if diagnostic:
         meta.update(schema='nzrt-test-clip-1',label='equipment_test',clip_policy='forward_2s',test_source=source,zero_filled_samples=int(missing))
        with self.server.commit_lock:
         base.publish(path,content);base.publish(path.with_suffix('.json'),(json.dumps(meta,indent=2,sort_keys=True)+'\n').encode())
        print(f'SAVED {path} samples={n//2} continuous={meta["capture_valid"]}',flush=True)
        return self.reply(200,'OK '+expected)
       except FileExistsError:return self.reply(409,'Conflicting clip')
       except (OSError,TimeoutError):return self.reply(500,'Storage or transfer failed')
     return Handler

    original_serve = Server.serve_forever
    base_handler = Handler

    def serve_with_pass1(server, *args, **kwargs):
        current = server.RequestHandlerClass
        base = SimpleNamespace(Handler=current, publish=publish, fnv=fnv)
        root = Path(os.environ.get('NZRT_BAT_ROOT', Path.home() / 'Documents' / 'Bat'))
        extended = extended_handler(base, root / 'Models' / 'RT')
        # A legacy launcher may have installed its own handler after creating Server.
        # Preserve those routes, including custom controls and diagnostic uploads.
        has_rt_launcher = current is not base_handler and hasattr(current, 'do_GET')

        class CompatibleHandler(extended):
            def do_GET(self):
                if self.path == '/pass1-version':
                    return super().do_GET()
                control = re.fullmatch(r'/rt-control/([0-9a-f]{12})', self.path)
                if has_rt_launcher and control and self.authorized():
                    request = self.server.root / 'RT_Controls' / (control[1] + '.json')
                    try:
                        entry = json.loads(request.read_bytes())
                    except (FileNotFoundError, ValueError):
                        entry = {}
                    if str(entry.get('command', '')).startswith('pass '):
                        return super().do_GET()
                if hasattr(current, 'do_GET') and (has_rt_launcher or not (
                    control or re.fullmatch(r'/rt-model/[0-9a-f]{64}', self.path)
                )):
                    return current.do_GET(self)
                return super().do_GET()

            def do_POST(self):
                if has_rt_launcher:
                    pass_ack = self.path.startswith('/rt-control-ack/') and self.headers.get('X-NZRT-Pass')
                    pass_clip = self.path == '/rt-clip' and self.headers.get('X-First-Pass')
                    if not (pass_ack or pass_clip):
                        return current.do_POST(self)
                return super().do_POST()

        server.RequestHandlerClass = CompatibleHandler
        print('PASS-1 receiver ready on port', server.server_port, flush=True)
        try:
            return original_serve(server, *args, **kwargs)
        finally:
            server.RequestHandlerClass = current

    Server.serve_forever = serve_with_pass1

_install_pass1_routes()

if __name__=='__main__': main()
