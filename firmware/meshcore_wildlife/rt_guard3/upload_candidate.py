"""Explicit USB deployment: identify GUARD-2, back up 8 MB flash, then upload built candidate."""
import argparse,hashlib,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from prepare_build import HERE,ENV,sha

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path);ap.add_argument('--port');a=ap.parse_args()
 project=a.project or Path((HERE/'last_candidate.txt').read_text().strip())
 r=json.loads((project/'guard3_receipt.json').read_text())
 if r['status']!='compiled_not_hardware_verified':raise ValueError('Build candidate first.')
 for group in ('sources','configuration'):
  for name,h in r[group].items():
   if sha(project/name)!=h:raise ValueError('Source/config changed since build: '+name)
 image=project/'.pio'/'build'/ENV/'firmware.bin'
 if sha(image)!=r['image_sha256']:raise ValueError('Firmware image differs from build receipt.')
 import serial
 from serial.tools import list_ports
 for p in list_ports.comports():print(p.device,p.description)
 port=a.port or input('RT COM port (close serial monitors): ').strip()
 if port.isdigit():port='COM'+port
 folder=project/'RT_Build_Receipts'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True)
 # Native USB can reset the board; refuse unknown firmware, never silently flash.
 with serial.Serial(port=None,baudrate=115200,timeout=.25,write_timeout=3) as ser:
  ser.dtr=False;ser.rts=False;ser.port=port;ser.open();time.sleep(2);ser.reset_input_buffer();ser.write(b'\nnzrt status\n')
  deadline=time.monotonic()+20;data=bytearray()
  while time.monotonic()<deadline:
   data.extend(ser.read(4096))
   if b'NZRT DIAG build=NZRT-J4-GUARD-2 ' in data:break
  (folder/'before_serial.txt').write_bytes(data)
  if b'NZRT DIAG build=NZRT-J4-GUARD-2 ' not in data:raise ValueError('GUARD-2 identity not confirmed; nothing uploaded.')
 backup=folder/'flash_before.bin'
 with (folder/'backup.log').open('wb') as log:
  subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','--port',port,'--baud','460800','read_flash','0','8388608',str(backup)],stdout=log,stderr=subprocess.STDOUT,check=True)
 if backup.stat().st_size!=8388608:raise ValueError('Incomplete flash backup; nothing uploaded.')
 deploy={'status':'backed_up','port':port,'backup':str(backup),'backup_sha256':sha(backup),'candidate_sha256':sha(image),'hardware_verified':False}
 receipt=folder/'deployment.json';receipt.write_text(json.dumps(deploy,indent=2)+'\n')
 with (folder/'upload.log').open('wb') as log:
  subprocess.run([sys.executable,'-m','platformio','run','-d',str(project),'-e',ENV,'-t','nobuild','-t','upload','--upload-port',port],stdout=log,stderr=subprocess.STDOUT,check=True)
 deploy['status']='uploaded_requires_board_test';receipt.write_text(json.dumps(deploy,indent=2)+'\n')
 print('Uploaded. Run the new receiver, then Run Loaded Test.cmd.');print('Private deployment receipt:',receipt)
 print('Rollback, same board only:');print(f'"{sys.executable}" -m esptool --chip esp32s3 --port {port} write_flash 0 "{backup}"')
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);sys.exit(1)
