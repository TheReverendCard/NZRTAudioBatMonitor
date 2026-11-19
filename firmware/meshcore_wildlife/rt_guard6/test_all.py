"""Portable GUARD6 source-integrity, native policy and receiver checks; no device access."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
HERE=Path(__file__).resolve().parent
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--compiler',default='c++');args=ap.parse_args()
    for name,expected in json.loads((HERE/'source_manifest.json').read_text()).items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==expected,name
    with tempfile.TemporaryDirectory() as td:
        work=Path(td)
        shutil.copytree(HERE/'tests/stubs',work,dirs_exist_ok=True)
        for name in json.loads((HERE/'host_sources.json').read_text()):shutil.copy2(HERE/'nzrt'/name,work/name)
        reference=(HERE/'tests/RTFeaturesSchema1.h').read_text().replace('namespace RTFeatures {','namespace RTFeaturesReference {')
        (work/'RTFeaturesReference.h').write_text(reference)
        for case in ('features','spool','journal','worker','upload','codec_probe'):
            exe=work/(case+('.exe' if os.name=='nt' else ''))
            src=HERE/'tests'/(case+'.cpp')
            if Path(args.compiler).stem.lower()=='cl':
                command=[args.compiler,'/nologo','/EHsc','/O2','/std:c++17','/fp:precise','/D_CRT_SECURE_NO_WARNINGS','/I'+str(work),str(src),'/Fe:'+str(exe),'/Fo:'+str(work/(case+'.obj'))]
            else:command=[args.compiler,'-std=c++17','-O2','-I'+str(work),str(src),'-o',str(exe)]
            subprocess.run(command,cwd=work,check=True)
            if case!='codec_probe':subprocess.run([str(exe)],check=True,timeout=90)
        env=dict(os.environ,RT_CODEC_PROBE=str(work/('codec_probe.exe' if os.name=='nt' else 'codec_probe')))
        subprocess.run([sys.executable,str(HERE/'tests/test_transport.py')],env=env,check=True,timeout=90)
    print('GUARD6 source, native and receiver checks passed; no board was opened or flashed.')
if __name__=='__main__':main()
