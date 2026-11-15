"""Stage a private GUARD-4 candidate from exact GUARD-3 sources. Never flash."""
import argparse,hashlib,json,os,shutil,subprocess,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
from modify import HERE,BASE,NEW,transform,digest
ENV='NZRT_Xiao_S3_WIO_wildlife_repeater'
BAT=Path(os.getenv('NZRT_BAT_ROOT',Path.home()/'Documents'/'Bat'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def choose():
 # The last successful GUARD-3 build has a durable receipt in the Bat folder.
 choices=[];hint=BAT/'Firmware'/'GUARD3_Tools'/'last_candidate.txt'
 if hint.is_file():
  p=Path(hint.read_text(encoding='utf8').strip())
  if (p/'platformio.ini').is_file():choices.append(p)
 for p in sorted((BAT/'Firmware'/'GUARD3').glob('*'),reverse=True):
  if (p/'platformio.ini').is_file() and p not in choices:choices.append(p)
 if choices:
  print('Using most recent GUARD-3 candidate:',choices[0]);return choices[0]
 return Path(input('GUARD-3 project folder containing platformio.ini: ').strip().strip('"'))
def stage(source,dest):
 source=source.resolve();dest=dest.resolve()
 if not (source/'platformio.ini').is_file():raise ValueError('Select the compiled GUARD3 project containing platformio.ini, not the downloaded patch folder.')
 if dest.exists() or source==dest or source in dest.parents or dest in source.parents:raise ValueError('Destination must be new and outside source.')
 for n,h in BASE.items():
  p=source/'nzrt'/n
  if p.is_symlink() or not p.is_file() or digest(p.read_text(encoding='utf8'))!=h:raise ValueError('Unrecognised GUARD-3 source/dependency: '+n+'. Original project untouched.')
 for n in NEW:
  if (source/'nzrt'/n).exists():raise ValueError('Unexpected new-version header in GUARD-3 source: '+n)
 def ignore(folder,names):
  return [n for n in names if n in ('.git','.pio','.venv','__pycache__','RT_Build_Receipts','PreUpdate_Backup') or 'backup' in n.lower() or n.lower().endswith('.log')]
 shutil.copytree(source,dest,ignore=ignore)
 backup=dest/'PreUpdate_Backup';backup.mkdir()
 with zipfile.ZipFile(backup/'previous_sources.zip','w',zipfile.ZIP_DEFLATED) as z:
  for p in (source/'nzrt').rglob('*'):
   if p.is_file() and not p.is_symlink():z.write(p,p.relative_to(source))
  for p in source.glob('platformio*.ini'):z.write(p,p.name)
  if (source/'merge-bin.py').is_file():z.write(source/'merge-bin.py','merge-bin.py')
 for n in BASE:(dest/'nzrt'/n).write_text(transform(n,(HERE/'base'/n).read_text(encoding='utf8')),encoding='utf8')
 for n in NEW:shutil.copy2(HERE/n,dest/'nzrt'/n)
 return {'source_project':str(source),'candidate_project':str(dest),'backup':str(backup/'previous_sources.zip'),'backup_sha256':sha(backup/'previous_sources.zip'),'status':'staged_not_compiled','flash_performed':False,'hardware_verified':False,'sources':{str(p.relative_to(dest)):sha(p) for p in sorted((dest/'nzrt').rglob('*')) if p.is_file()},'configuration':{p.name:sha(p) for p in sorted(dest.glob('platformio*.ini'))}}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--stage-only',action='store_true');a=ap.parse_args()
 source=a.project or choose();dest=a.out or BAT/'Firmware'/'GUARD4'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 receipt=stage(source,dest);rp=dest/'guard4_receipt.json';rp.write_text(json.dumps(receipt,indent=2)+'\n')
 from merge_upload_fix import ensure_merge_script
 receipt['merge_script']=ensure_merge_script(dest);rp.write_text(json.dumps(receipt,indent=2)+'\n')
 print('Source preserved:',source);print('Private candidate:',dest)
 if not a.stage_only:
  receipt['status']='build_failed'
  try:
   with (dest/'guard4_build.log').open('wb') as log:subprocess.run([sys.executable,'-m','platformio','run','-d',str(dest),'-e',ENV],stdout=log,stderr=subprocess.STDOUT,check=True)
   image=dest/'.pio'/'build'/ENV/'firmware.bin';receipt.update(status='compiled_not_hardware_verified',image_sha256=sha(image),elf_sha256=sha(image.with_suffix('.elf')))
  except subprocess.CalledProcessError:
   print('\n'.join((dest/'guard4_build.log').read_text(errors='replace').splitlines()[-40:]),flush=True);raise
  finally:rp.write_text(json.dumps(receipt,indent=2)+'\n')
  (HERE/'last_candidate.txt').write_text(str(dest.resolve())+'\n')
 print('Receipt:',rp);print('No board flashed. Keep source backup and build outputs private.')
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);sys.exit(1)
