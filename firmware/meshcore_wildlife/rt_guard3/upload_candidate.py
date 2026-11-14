"""Explicit USB deployment: identify GUARD-2, back up 8 MB flash, then upload built candidate."""
import argparse,hashlib,json,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
from prepare_build import HERE,ENV,sha
from serial_link import Link,identify,IdentityError

def check_board(serial_module, port, folder):
 """Record every attempt, including open/transport failures, before any flash tool."""
 report={'status':'not_confirmed','port':port,'expected_build':'NZRT-J4-GUARD-2'}
 print('Checking RT identity (up to 45 seconds).  Connection report:',folder,flush=True)
 try:
  with (folder/'before_serial.txt').open('w',encoding='utf8',buffering=1) as log:
   with serial_module.Serial(port=None,baudrate=115200,timeout=.25,write_timeout=3) as ser:
    # Preserve the control-line settings already used by the successful compare tool.
    ser.dtr=False;ser.rts=False;ser.port=port;ser.open()
    # Keep boot/status output in the log instead of discarding the input buffer.
    time.sleep(2)
    report.update(identify(Link(ser,log),'NZRT-J4-GUARD-2'))
 except IdentityError as e:
  report.update(e.report);report['error']=str(e)
  raise ValueError(str(e)+' Connection report: '+str(folder/'identity.json')) from e
 except (Exception,KeyboardInterrupt) as e:
  report.update(status='connection_failed',error=str(e) or type(e).__name__)
  raise
 finally:
  (folder/'identity.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
 print('Confirmed:',report['observed_build'],'session='+report['session'],flush=True)
 return report

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
 identity=check_board(serial,port,folder)
 backup=folder/'flash_before.bin'
 with (folder/'backup.log').open('wb') as log:
  subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','--port',port,'--baud','460800','read_flash','0','8388608',str(backup)],stdout=log,stderr=subprocess.STDOUT,check=True)
 if backup.stat().st_size!=8388608:raise ValueError('Incomplete flash backup; nothing uploaded.')
 deploy={'status':'backed_up','port':port,'identity':identity,'backup':str(backup),'backup_sha256':sha(backup),'candidate_sha256':sha(image),'hardware_verified':False}
 receipt=folder/'deployment.json';receipt.write_text(json.dumps(deploy,indent=2)+'\n')
 with (folder/'upload.log').open('wb') as log:
  subprocess.run([sys.executable,'-m','platformio','run','-d',str(project),'-e',ENV,'-t','nobuild','-t','upload','--upload-port',port],stdout=log,stderr=subprocess.STDOUT,check=True)
 deploy['status']='uploaded_requires_board_test';receipt.write_text(json.dumps(deploy,indent=2)+'\n')
 print('Uploaded. Run the new receiver, then Run Loaded Test.cmd.');print('Private deployment receipt:',receipt)
 print('Rollback, same board only:');print(f'"{sys.executable}" -m esptool --chip esp32s3 --port {port} write_flash 0 "{backup}"')
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);sys.exit(1)
