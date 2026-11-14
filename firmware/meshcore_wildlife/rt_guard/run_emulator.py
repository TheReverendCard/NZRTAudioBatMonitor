"""Build, boot and validate both S3 guests. Never uploads or opens a COM port."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys
from pathlib import Path
from test_gate import prepare,HERE
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(out,emu):
 out=out.resolve();out.mkdir(parents=True,exist_ok=False);idf=Path(os.environ['IDF_PATH'])/'tools/idf.py'
 emu=Path(shutil.which(emu) or emu).resolve();rec={'ready_to_deploy':False,'emulator':subprocess.check_output([str(emu),'--version'],text=True).strip(),'emulator_sha256':sha(emu),'cases':{}}
 try:
  p=out/'project';shutil.copytree(HERE/'bench',p);m=p/'main';prepare(m)
  for case,marker in [('detector','NZRT_GUARD_PASS'),('restart','NZRT_RESTART_GUARD_PASS')]:
   if case=='restart':
    shutil.copy2(HERE/'guard_task.inc',m/'guard_task.inc');shutil.copy2(HERE/'test/restart_probe.cpp',m/'restart.cpp')
    cm=m/'CMakeLists.txt';cm.write_text(cm.read_text().replace('"WildlifeDetector.cpp" "probe.cpp"','"restart.cpp"'))
   stem=out/case;stem.mkdir();img=p/'build/all.bin'
   with (stem/'build.log').open('w') as f:
    for args in (['-DIDF_TARGET=esp32s3','build'],['merge-bin','-o',str(img)]):
     subprocess.run([sys.executable,str(idf),*args],cwd=p,stdout=f,stderr=subprocess.STDOUT,timeout=1200,check=True)
   uart=stem/'uart.log'
   with uart.open('w') as f:subprocess.run([str(emu),'--chip','esp32s3','--firmware',str(img),'--elf',str(p/'build/guard_test.elf'),'--timeout','150s','--exit-on',marker],stdout=f,stderr=subprocess.STDOUT,timeout=190,check=True)
   log=uart.read_text(errors='replace')
   pattern=r'^NZRT_GUARD_PASS checks=[1-9]\d*\s*$' if case=='detector' else r'^NZRT_RESTART_GUARD_PASS retained_reason=DSP repeated_stall_no_reboot=1\s*$'
   matches=re.findall(pattern,log,re.M)
   if len(matches)!=1 or any(x in log for x in ('Firmware abort:', 'Task watchdog got triggered','Guru Meditation Error','Backtrace:', '\x00')):raise ValueError('missing, duplicate, or faulted guest result: '+case)
   rec['cases'][case]={'result':matches[0].strip(),'image_sha256':sha(img),'uart_sha256':sha(uart)}
  rec['status']='passed'
 except BaseException as e:rec['status']='failed';rec['reason']=str(e);raise
 finally:(out/'receipt.json').write_text(json.dumps(rec,indent=2)+'\n')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('new_output',type=Path);a.add_argument('--emu',default='esp-emu');v=a.parse_args();run(v.new_output,v.emu)
