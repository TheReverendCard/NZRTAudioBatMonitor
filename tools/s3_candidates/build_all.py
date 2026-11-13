"""Fully link each exported ESP32-S3 probe in an activated ESP-IDF 5.x environment. Never flash."""
import argparse, hashlib, json, os, subprocess, sys
from pathlib import Path
from build_project import project
from export_all import write
def main(index,out):
    index=index.resolve(); home=index.parent
    entries=json.loads(index.read_text())['rows']
    idf=Path(os.environ.get('IDF_PATH',''))/'tools/idf.py'
    if not idf.is_file():raise RuntimeError('Activate the ESP-IDF 5.x environment first.')
    out.mkdir(parents=True,exist_ok=False)
    seen=set();results=[]; failures=0
    for row in entries:
        if row['status'] in ('blocked','unsupported','no_local_run'):
            results.append(row); failures+=1;continue
        if row['status']!='source_exported':continue
        bundle=(home/row['bundle']).resolve()
        if not bundle.is_relative_to(home):raise ValueError('bundle path outside export root')
        if bundle in seen:continue
        seen.add(bundle); dest=out/(row['profile']+'_'+bundle.name[:16])
        result=dict(bundle=row['bundle'],profile=row['profile'],status='failed')
        try:
            project(bundle,dest)
            with (dest/'build.log').open('w') as f:
                for args in (['set-target','esp32s3'],['build']):
                    subprocess.run([sys.executable,str(idf),*args],cwd=dest,stdout=f,stderr=subprocess.STDOUT,check=True)
            binary=dest/'build/s3_export_probe.bin'
            result.update(status='linked_bench_only',image_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),bytes=binary.stat().st_size)
        except Exception as e:result['error']=str(e); failures+=1
        results.append(result);write(out/'build_receipt.json',dict(promotion_ready=False,results=results))
    write(out/'build_receipt.json',dict(promotion_ready=False,results=results))
    return int(bool(failures or not seen))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('index',type=Path);p.add_argument('new_directory',type=Path);a=p.parse_args()
    sys.exit(main(a.index,a.new_directory.resolve()))
