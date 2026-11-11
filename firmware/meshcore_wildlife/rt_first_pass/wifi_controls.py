"""Queue an idempotent command for a known RT to collect on its next WiFi check."""
import json,re,uuid
from pathlib import Path
import os
ROOT=Path(os.environ.get('NZRT_BAT_ROOT',Path.home()/'Documents'/'Bat'))

def main():
 cfg=ROOT/'bat_config.json';c=json.loads(cfg.read_text(encoding='utf-8-sig')) if cfg.exists() else {}
 default=c.get('receiver',{}).get('backup_root',str(ROOT/'WiFi_Backup'))
 root=Path(input('Receiver data folder ['+default+']: ').strip().strip('"') or default)
 devices=sorted(p.name for p in (root/'RT').glob('*') if p.is_dir() and re.fullmatch('[0-9a-f]{12}',p.name))
 for i,d in enumerate(devices,1):print(f'{i}: Xiao RT {d}')
 choice=input('Choose RT number, or 12-character device ID: ').strip()
 device=devices[int(choice)-1] if choice.isdigit() and 1<=int(choice)<=len(devices) else choice
 if not re.fullmatch('[0-9a-f]{12}',device):raise ValueError('Invalid device ID')
 print('11 First-pass status or selection')
 print('1 WAV ON\n2 WAV OFF\n3 Shadow mode\n4 Promote a specific model\n5 Fetch a staged model\n6 Record now\n7 Bench on (1 hour)\n8 Bench off / automatic schedule\n9 Periodic sample interval\n10 Periodic off')
 option=input('Choice: ').strip();cmd={'1':'wav on','2':'wav off','3':'mode shadow','6':'record now','7':'test on','8':'test off','10':'scan off'}.get(option)
 if option=='11':
  print('Last board ACK:',(root/'RT_Controls'/(device+'.ack.json')).read_text() if (root/'RT_Controls'/(device+'.ack.json')).is_file() else 'none')
  active=input('Active: status, legacy, evolved or audible: ').strip().lower()
  if active=='status':cmd='pass status'
  elif active in ('legacy','evolved','audible'):
   shadow=input('Shadow: off or a different detector: ').strip().lower()
   if shadow not in ('off','legacy','evolved','audible') or shadow==active:raise ValueError('Invalid shadow')
   cmd='pass '+active+' '+shadow
 if option=='9':
  seconds=int(input('Interval in seconds (10..86400): '))
  if not 10<=seconds<=86400:raise ValueError('Interval outside supported range')
  cmd=f'scan every {seconds}'
 if option in ('4','5'):
  model=input('Model SHA256 (or builtin-wav-mlp-v01 for built-in promotion): ').strip()
  if not re.fullmatch('[0-9a-f]{64}',model) and not (option=='4' and model=='builtin-wav-mlp-v01'):raise ValueError('Invalid model ID')
  cmd=('mode active ' if option=='4' else 'model fetch ')+model
 if not cmd:raise ValueError('Invalid choice')
 folder=root/'RT_Controls';folder.mkdir(parents=True,exist_ok=True);path=folder/(device+'.json');ack=folder/(device+'.ack.json')
 if path.exists():
  old=json.loads(path.read_text());done=json.loads(ack.read_text()) if ack.exists() else {}
  if old['id']!=done.get('id'):raise ValueError('A previous command is still pending. Wait for acknowledgement or inspect '+str(path))
 entry={'id':uuid.uuid4().hex,'command':cmd,'device':device};tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(entry,indent=2)+'\n');tmp.replace(path)
 c.setdefault('receiver',{})['backup_root']=str(root);tmp=cfg.with_suffix('.tmp');tmp.write_text(json.dumps(c,indent=2)+'\n');tmp.replace(cfg)
 print('Queued:',cmd);print('TEST-2 polls about every 10 seconds in bench mode and for the first 10 minutes after boot; normal mode uses 30 minutes. Accepted commands produce:',ack)
 print('Model downloads wait for daytime idle and return to shadow mode. Check the journal for completion.')
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);raise SystemExit(1)
