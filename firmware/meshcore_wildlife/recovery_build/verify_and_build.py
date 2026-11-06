"""Verify recovered RT source, then compile only. Never uploads or erases a device."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

TARGET = 'NZRT_Xiao_S3_WIO_wildlife_repeater'
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('project', type=Path)
    ap.add_argument('--check-only', action='store_true')
    args = ap.parse_args()
    root = args.project.resolve()
    expected = json.loads(Path(__file__).with_name('expected_sources.json').read_text())
    problems = [p for p, sha in expected.items() if not (root/p).is_file() or digest(root/p) != sha]
    if problems:
        print('STOP: missing or different recovered files. No build or upload performed.')
        print('\n'.join(problems))
        return 2
    print('All 14 recovered source/configuration hashes match.')
    if args.check_only:
        return 0
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = root/'RT_Build_Receipts'/stamp
    out.mkdir(parents=True)
    command = [sys.executable, '-m', 'platformio', 'run', '-d', str(root), '-e', TARGET]
    # Build logs remain local: compiler output can include private build flags.
    with (out/'build.log').open('w', encoding='utf-8') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    receipt = {'schema':1, 'target':TARGET, 'created_utc':stamp,
               'exit_code':result.returncode, 'sources':expected,
               'status':'build_failed', 'flashed':False,
               'limitations':'Source subset verified; upstream/dependency and board identity not fully locked. Not proof of running device binary.'}
    for name, cmd in [('dependencies', [sys.executable,'-m','platformio','pkg','list','-d',str(root),'-e',TARGET]),
                      ('platformio_version',[sys.executable,'-m','platformio','--version'])]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        (out/(name+'.txt')).write_text(r.stdout+r.stderr, encoding='utf-8')
    binary = root/'.pio'/'build'/TARGET/'firmware.bin'
    if result.returncode == 0 and binary.is_file():
        import shutil
        shutil.copy2(binary, out/'firmware.bin')
        receipt.update(status='compiled_not_hardware_verified', firmware_sha256=digest(binary))
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print('Receipt:',out)
    print('Status:',receipt['status'])
    print('Keep this directory private: binary/logs may contain receiver configuration.')
    return 0 if receipt['status']=='compiled_not_hardware_verified' else 1
if __name__ == '__main__':
    raise SystemExit(main())
