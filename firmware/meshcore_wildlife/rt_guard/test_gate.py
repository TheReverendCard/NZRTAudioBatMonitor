"""Regression target: real PASS-1 detector translation unit + actual recovery policy."""
import argparse,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from modify import HERE,BASE,transform
def prepare(dst):
    recipe=HERE.parent/'rt_first_pass/changes.json'
    if recipe.is_file() and {n:v['after'] for n,v in json.loads(recipe.read_text()).items()}!=BASE:
        raise ValueError('PASS-1 upstream source changed; rebase the guard tests before release')
    for n in BASE:(dst/n).write_text(transform(n,(HERE/'base'/n).read_text()))
    for n in ('GuardPolicy.h','GuardSignals.h'):shutil.copy2(HERE/n,dst/n)
    for n in ('WildlifeScoring.h','probe.cpp'):shutil.copy2(HERE/'test'/n,dst/n)
def host(cxx):
    with tempfile.TemporaryDirectory() as td:
        d=Path(td);prepare(d)
        exe=d/'guard_test';subprocess.run([cxx,'-std=c++11','-O2','-DNZRT_HOST_TEST','-I'+str(HERE/'test/host'),str(d/'WildlifeDetector.cpp'),str(d/'probe.cpp'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--bench',type=Path);a.add_argument('--cxx',default='c++');o=a.parse_args()
    if o.bench:
        shutil.copytree(HERE/'bench',o.bench);prepare(o.bench/'main')
    else:host(o.cxx)
