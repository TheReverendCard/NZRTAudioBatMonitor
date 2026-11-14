"""Prepare a separate GUARD-2 bench checkout and build it. No serial/flash operation."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from modify import HERE,BASE,transform,digest,guard1
from guard2 import upgrade
ENV='NZRT_Xiao_S3_WIO_wildlife_repeater'
def stage(source,dest):
 source=source.resolve();dest=dest.resolve()
 if dest==source or source in dest.parents or dest in source.parents or dest.exists():raise ValueError('Choose a new directory outside the source tree')
 ini=source/'platformio.local.ini'
 if not (source/'platformio.ini').is_file() or not ini.is_file() or ENV not in ini.read_text():raise ValueError('Missing PASS-1 PlatformIO project')
 converted={};versions=set()
 for n,h in BASE.items():
    if (source/'nzrt'/n).is_symlink():raise ValueError('Linked source: '+n)
    local=(source/'nzrt'/n).read_text(encoding='utf8')
    original=(HERE/'base'/n).read_text(encoding='utf8')
    if digest(local)==h:versions.add('PASS-1');converted[n]=transform(n,local)
    elif digest(local)==digest(guard1(n,original)):versions.add('GUARD-1');converted[n]=upgrade(n,local)
    else:raise ValueError('Unknown source revision: '+n)
 if len(versions)!=1:raise ValueError('Mixed firmware source revisions')
 for header in ('GuardPolicy.h','GuardSignals.h'):
    hp=source/'nzrt'/header
    if versions=={'GUARD-1'}:
       if hp.is_symlink() or hp.read_text()!= (HERE/header).read_text():raise ValueError('Modified GUARD-1 header: '+header)
    elif hp.exists():raise ValueError('Unexpected guard header in PASS-1 tree: '+header)
 def ignores(folder,names):
    return [n for n in names if n in ('.git','.pio','.venv','__pycache__','.nzrt-backups','RT_Build_Receipts','guard_build_receipt.json') or 'backup' in n.lower() or n.lower().endswith(('.log','.bin.tmp'))]
 # Copy only the local project; PIO will rebuild its caches.
 shutil.copytree(source,dest,ignore=ignores)
 for n,new in converted.items():(dest/'nzrt'/n).write_text(new,encoding='utf8')
 for n in ('GuardPolicy.h','GuardSignals.h'):
    shutil.copy2(HERE/n,dest/'nzrt'/n)
 return dest
def main():
 a=argparse.ArgumentParser();a.add_argument('--project',type=Path,default=Path.home()/'NZRTAudioBatMonitor-meshcore/NZRT-MeshCore-NZBat-BandMonitor')
 a.add_argument('--out',type=Path);v=a.parse_args();root=v.project.resolve()
 dst=v.out or root.parent/('GUARD2_Bench_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
 dst=stage(root,dst);receipt={'status':'build_failed','hardware_verified':False,'flash_performed':False,'candidate_sources':{n:digest((dst/'nzrt'/n).read_text()) for n in [*BASE,'GuardPolicy.h','GuardSignals.h']}}
 print('Private candidate project:',dst,flush=True)
 try:
    with (dst/'guard_build.log').open('wb') as f:subprocess.run([sys.executable,'-m','platformio','run','-d',str(dst),'-e',ENV],stdout=f,stderr=subprocess.STDOUT,check=True)
    image=dst/'.pio/build'/ENV/'firmware.bin'
    receipt.update(status='compiled_bench_only',image_sha256=hashlib.sha256(image.read_bytes()).hexdigest())
 finally:(dst/'guard_build_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('Compiled for bench. No board was flashed.')
if __name__=='__main__':main()
