"""Stage a private GUARD-3 candidate from exact GUARD-2 sources. Never flash."""
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
from modify import HERE,BASE,transform,digest
ENV='NZRT_Xiao_S3_WIO_wildlife_repeater'
BAT=Path(os.getenv('NZRT_BAT_ROOT',Path.home()/'Documents'/'Bat'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def choose():
 parent=Path.home()/'NZRTAudioBatMonitor-meshcore'
 choices=sorted((p for p in parent.glob('GUARD2_Bench_*') if (p/'platformio.ini').is_file()),key=lambda p:p.name,reverse=True)
 for i,p in enumerate(choices,1):print(f'{i}: {p}')
 value=input('Installed GUARD-2 source project: choose number or paste full folder: ').strip().strip('"')
 return choices[int(value)-1] if value.isdigit() and 1<=int(value)<=len(choices) else Path(value)
def stage(source,dest):
 source=source.resolve();dest=dest.resolve()
 if not (source/'platformio.ini').is_file():raise ValueError('Select the generated GUARD2_Bench project containing platformio.ini, not the downloaded patch folder.')
 if dest.exists() or source==dest or source in dest.parents or dest in source.parents:raise ValueError('Destination must be new and outside source.')
 for n,h in BASE.items():
  p=source/'nzrt'/n
  if p.is_symlink() or not p.is_file() or digest(p.read_text(encoding='utf8'))!=h:raise ValueError('Unrecognised GUARD-2 source/dependency: '+n+'. Original project untouched.')
 def ignore(folder,names):
  return [n for n in names if n in ('.git','.pio','.venv','__pycache__','RT_Build_Receipts','PreUpdate_Backup') or 'backup' in n.lower() or n.lower().endswith('.log')]
 shutil.copytree(source,dest,ignore=ignore)
 backup=dest/'PreUpdate_Backup';backup.mkdir()
 with zipfile.ZipFile(backup/'previous_sources.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in (source/'nzrt').rglob('*'):
   if p.is_file() and not p.is_symlink():z.write(p,p.relative_to(source))
  for p in source.glob('platformio*.ini'):z.write(p,p.name)
 for n in BASE:(dest/'nzrt'/n).write_text(transform(n,(HERE/'base'/n).read_text()),encoding='utf8')
 for n in ('RTClipLease.h','RTJournalPolicy.h','RTFeatureControl.h'):shutil.copy2(HERE/n,dest/'nzrt'/n)
 return {'source_project':str(source),'candidate_project':str(dest),'backup':str(backup/'previous_sources.zip'),'backup_sha256':sha(backup/'previous_sources.zip'),'status':'staged_not_compiled','flash_performed':False,'hardware_verified':False,'sources':{str(p.relative_to(dest)):sha(p) for p in sorted((dest/'nzrt').rglob('*')) if p.is_file()},'configuration':{p.name:sha(p) for p in sorted(dest.glob('platformio*.ini'))}}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--stage-only',action='store_true');a=ap.parse_args()
 source=a.project or choose();dest=a.out or BAT/'Firmware'/'GUARD3'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 receipt=stage(source,dest);rp=dest/'guard3_receipt.json';rp.write_text(json.dumps(receipt,indent=2)+'\n')
 print('Source preserved:',source);print('Private candidate:',dest)
 if not a.stage_only:
  receipt['status']='build_failed'
  try:
   with (dest/'guard3_build.log').open('wb') as log:subprocess.run([sys.executable,'-m','platformio','run','-d',str(dest),'-e',ENV],stdout=log,stderr=subprocess.STDOUT,check=True)
   image=dest/'.pio'/'build'/ENV/'firmware.bin';receipt.update(status='compiled_not_hardware_verified',image_sha256=sha(image))
  finally:rp.write_text(json.dumps(receipt,indent=2)+'\n')
  (HERE/'last_candidate.txt').write_text(str(dest.resolve())+'\n')
 print('Receipt:',rp);print('No board flashed. Keep source backup and build outputs private.')
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);sys.exit(1)
