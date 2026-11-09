"""Queue an idempotent command for a known RT to collect on its next WiFi check."""
import json,re,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
 cfg=ROOT/'bat_config.json';c=json.loads(cfg.read_text(encoding='utf-8-sig')) if cfg.exists() else {}
 default=c.get('receiver',{}).get('backup_root',str(ROOT/'WiFi_Backup'))
 root=Path(input('Receiver data folder ['+default+']: ').strip().strip('"') or default)
 devices=sorted(p.name for p in (root/'RT').glob('*') if p.is_dir() and re.fullmatch('[0-9a-f]{12}',p.name))
 for i,d in enumerate(devices,1):print(f'{i}: Xiao RT {d}')
 choice=input('Choose RT number, or 12-character device ID: ').strip()
 device=devices[int(choice)-1] if choice.isdigit() and 1<=int(choice)<=len(devices) else choice
 if not re.fullmatch('[0-9a-f]{12}',device):raise ValueError('Invalid device ID')
 print('1 WAV ON\n2 WAV OFF\n3 Shadow mode\n4 Promote a specific model\n5 Fetch a staged model')
 option=input('Choice: ').strip();cmd={'1':'wav on','2':'wav off','3':'mode shadow'}.get(option)
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
 print('Queued:',cmd);print('The RT checks about every 30 minutes. Accepted commands produce:',ack)
 print('Model downloads wait for daytime idle and return to shadow mode. Check the journal for completion.')
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);raise SystemExit(1)
