"""Source-verified RT MLP updater. Build first, preserve journal, then flash and verify."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
TARGET='NZRT_Xiao_S3_WIO_wildlife_repeater';BUILD='NZRT-MLP-1-JOURNAL-2'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,data):
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8');temp.replace(path)
def config():
 p=ROOT/'bat_config.json';c=json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {'schema':1};return p,c

def prepare(project):
 expected=json.loads((HERE/'baseline_sources.json').read_text());desired=json.loads((HERE/'payload_hashes.json').read_text())
 for rel,h in desired.items():
  if sha(HERE/'payload'/rel)!=h:raise ValueError('Package checksum failed: '+rel)
 marker=project/'RT_MLP_Install.json';previous=json.loads(marker.read_text()) if marker.exists() else {}
 accepted=previous.get('installed_hashes',{})
 for rel,h in expected.items():
  p=project/rel
  if not p.is_file() or sha(p) not in {h,accepted.get(rel,'')}:
   raise ValueError('Source differs from verified baseline/last install: '+rel+'. No changes made.')
 for rel in desired:
  p=project/rel
  if p.exists() and rel not in expected and sha(p)!=accepted.get(rel):raise ValueError('Unexpected existing file: '+rel)
 ini=(project/'platformio.local.ini').read_text()
 if '  +<../nzrt/WildlifeML.cpp>' not in ini:
  if ini.count('  +<../nzrt/WildlifeMic.cpp>')!=1:raise ValueError('Ambiguous source filter')
  ini=ini.replace('  +<../nzrt/WildlifeMic.cpp>','  +<../nzrt/WildlifeMic.cpp>\n  +<../nzrt/WildlifeML.cpp>')
  ini=ini.replace('  -I nzrt','  -I nzrt\n  -D BOARD_HAS_PSRAM')
  ini=ini.replace('build_src_filter =','board_build.arduino.memory_type = qio_opi\nboard_build.psram_type = opi\nbuild_src_filter =')
 changes={rel:(HERE/'payload'/rel).read_bytes() for rel in desired};changes['platformio.local.ini']=ini.encode()
 return changes

def select_port(rt):
 from serial.tools import list_ports
 ports=list(list_ports.comports())
 if not ports:raise ValueError('No serial ports. Connect Xiao RT and close other Serial Monitors.')
 for i,p in enumerate(ports,1):print(f'{i}: {p.device} {p.description}')
 value=input('Choose list number or COM name ['+rt.get('port','COM8')+']: ').strip() or rt.get('port','COM8')
 if value.isdigit():
  if not 1<=int(value)<=len(ports):raise ValueError('Choose a displayed list number or COM8 etc.')
  value=ports[int(value)-1].device
 if value.upper() not in [p.device.upper() for p in ports]:raise ValueError('Port not listed')
 return value.upper()
def execute(cmd,path):
 env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PLATFORMIO_SETTING_ENABLE_TELEMETRY='No')
 with path.open('w',encoding='utf-8') as f:
  p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env)
  try:
   for line in p.stdout:print(line,end='');f.write(line)
   return p.wait()
  except BaseException:p.terminate();p.wait();raise

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--build-only',action='store_true');ap.add_argument('--project',type=Path);args=ap.parse_args()
 cfg,c=config();rt=c.setdefault('devices',{}).setdefault('rt',{})
 default=rt.get('project',str(Path.home()/'NZRTAudioBatMonitor-meshcore'/'NZRT-MeshCore-NZBat-BandMonitor'))
 project=args.project or Path(input('RT project [Enter uses '+default+']: ').strip().strip('"') or default)
 project=project.resolve();changes=prepare(project)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');report=ROOT/'Update_Reports'/('RT_MLP_'+stamp);report.mkdir(parents=True)
 port=None
 if not args.build_only:
  import rt_log_reader
  port=select_port(rt);print('Backing up the current RT journal before any source change...')
  data,meta=rt_log_reader.read_journal(port);(report/'before.txt').write_bytes(data);write_json(report/'before.json',meta)
  match=re.search(r'NZRT DIAG build=(\S+)',meta.get('status_reply',''))
  if not meta.get('complete') or not match or match[1] not in ['NZRT-FIELD-PILOT-5-WIFI-2-JOURNAL',BUILD]:raise ValueError('RT identity or complete journal backup not verified. Nothing changed.')
  rt.update(project=str(project),port=port,last_reported_firmware=match[1]);write_json(cfg,c)
 backup=report/'source_backup';backup.mkdir();existed={}
 marker=project/'RT_MLP_Install.json'
 if marker.exists():shutil.copy2(marker,backup/'RT_MLP_Install.json')
 for rel in changes:
  p=project/rel;existed[rel]=p.exists()
  if p.exists():q=backup/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
 write_json(report/'backup_manifest.json',{'project':str(project),'existed':existed,'backup_hashes':{r:sha(backup/r) for r,was in existed.items() if was}})
 # Preserve all existing flash images, not only application firmware. Keep private.
 images=project/'.pio'/'build'/TARGET
 if images.exists():
  rollback=report/'previous_build_images';rollback.mkdir()
  for p in images.glob('*.bin'):shutil.copy2(p,rollback/p.name)
 def restore():
  for rel,was in existed.items():
   p=project/rel
   if was:shutil.copy2(backup/rel,p)
   elif p.exists():p.unlink()
 try:
  for rel,data in changes.items():p=project/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
  cmd=[sys.executable,'-m','platformio','run','-d',str(project),'-e',TARGET]
  if execute(cmd,report/'build.log'):raise ValueError('Build failed; original sources restored. Device unchanged.')
 except BaseException:restore();raise
 binary=images/'firmware.bin'
 if not binary.is_file():restore();raise ValueError('Build returned success without firmware.bin')
 receipt={'schema':1,'build':BUILD,'target':TARGET,'utc':stamp,'project':str(project),'firmware_sha256':sha(binary),'installed_hashes':{r:sha(project/r) for r in changes},'source_baseline':json.loads((HERE/'baseline_sources.json').read_text()),'flashed':False,'hardware_verified':False}
 shutil.copy2(binary,report/'firmware.bin');write_json(project/'RT_MLP_Install.json',receipt);write_json(report/'receipt.json',receipt)
 if args.build_only:print('COMPILED ONLY. No flash. Receipt:',report);return
 if execute(cmd+['-t','upload','--upload-port',port],report/'upload.log'):
  raise ValueError('Upload failed; prepared sources and backups retained. Device state requires checking. '+str(report))
 receipt['flashed']=True;write_json(report/'receipt.json',receipt)
 import serial
 response=bytearray();conn=None
 for _ in range(20):
  try:conn=serial.Serial(port,115200,timeout=.2);break
  except serial.SerialException:time.sleep(1)
 if conn is None:raise ValueError('Upload finished but serial port did not return. See '+str(report))
 with conn as ser:
  time.sleep(3);ser.write(b'\nnzrt status\nnzrt ml status\nnzrt journal test\n');ser.flush();until=time.monotonic()+30
  while time.monotonic()<until:
   response.extend(ser.read(ser.in_waiting or 1))
   if b'NZRT JOURNAL_TEST result=PASS' in response and b'NZRT ML_STATUS enabled=1' in response and BUILD.encode() in response:break
 (report/'after.txt').write_bytes(response)
 if BUILD.encode() not in response or b'NZRT JOURNAL_TEST result=PASS' not in response or b'NZRT ML_STATUS enabled=1' not in response:
  raise ValueError('Flashed, but RT identity, journal or model worker startup did not pass. Inspect '+str(report/'after.txt'))
 receipt['startup_verified']=True;receipt['verification_scope']='build identity, journal append/readback, model worker allocation only; not acoustic/timing/overnight validation'
 write_json(report/'receipt.json',receipt);write_json(project/'RT_MLP_Install.json',receipt)
 rt.update(last_reported_firmware=BUILD,last_uploaded_firmware=BUILD,last_seen_utc=datetime.now(timezone.utc).isoformat());write_json(cfg,c)
 print('PASS: firmware identity, JOURNAL-2 readback and model worker startup. Acoustic/timing validation remains.')
 print('First installation defaults: shadow mode, WAV uploads OFF. Reports:',report)
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);raise SystemExit(1)
