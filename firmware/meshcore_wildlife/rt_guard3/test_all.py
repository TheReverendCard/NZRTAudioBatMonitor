import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from modify import HERE,emit

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path);a=ap.parse_args();results=[]
 with tempfile.TemporaryDirectory() as td:
  d=Path(td);emit(d)
  for p in (HERE/'tests/reference').iterdir():shutil.copy2(p,d/p.name)
  (d/'RTFeaturesReference.h').write_text((HERE/'base/RTFeatures.h').read_text().replace('namespace RTFeatures {','namespace RTFeaturesReference {'))
  for case in ('features','journal','worker'):
   exe=d/case;subprocess.run(['c++','-std=c++11','-O2','-I'+str(d),'-I'+str(HERE/'tests/stubs'),str(HERE/'tests'/(case+'.cpp')),'-o',str(exe)],check=True)
   output=subprocess.check_output([str(exe)],text=True,timeout=60).strip();print(output);results.append(output)
 subprocess.run([sys.executable,'-m','unittest','discover','-s',str(HERE/'tests'),'-p','test_*.py'],check=True)
 receipt={'host_tests':results,'workflow_tests':'passed','hardware_tested':False,'full_platformio_build':False,'s3_speedup_claimed':False}
 if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':main()
