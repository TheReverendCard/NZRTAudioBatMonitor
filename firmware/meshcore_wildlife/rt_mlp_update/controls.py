"""Small serial control menu using the shared Bat config and current port list."""
import time
import serial
from update import config,select_port,write_json

def main():
 cfg,c=config();rt=c.setdefault('devices',{}).setdefault('rt',{});port=select_port(rt);rt['port']=port;write_json(cfg,c)
 print('1 Status\n2 WAV uploads ON\n3 WAV uploads OFF\n4 Shadow mode\n5 Promote current model\n6 Fetch staged model over WiFi\n7 Restore built-in model (shadow)\n8 Run daytime model self-test')
 choice=input('Choice: ').strip();commands={'1':'nzrt ml status','2':'nzrt wav on','3':'nzrt wav off','4':'nzrt ml shadow','5':'nzrt ml active','7':'nzrt model builtin','8':'nzrt ml test'}
 if choice=='6':
  import re
  sha=input('SHA256 printed by Stage Model.bat: ').strip()
  if not re.fullmatch('[0-9a-f]{64}',sha):raise ValueError('Expected 64 lowercase hex characters')
  cmd='nzrt model fetch '+sha
 else:cmd=commands[choice]
 with serial.Serial(port,115200,timeout=.2) as ser:
  time.sleep(2);ser.write(('\n'+cmd+'\nnzrt ml status\n').encode());ser.flush();until=time.monotonic()+(120 if choice=='8' else 6)
  while time.monotonic()<until:
   data=ser.read(ser.in_waiting or 1)
   if data:
    text=data.decode('utf-8',errors='replace');print(text,end='')
    if choice=='8' and ('NZRT ML_TEST result=' in text or 'NZRT ML_TEST rejected' in text):break
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);raise SystemExit(1)
