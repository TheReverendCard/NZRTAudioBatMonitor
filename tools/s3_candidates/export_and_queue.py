"""Refresh exports, publish the S3 test queue, optionally start the owner's WSL worker."""
import argparse, json, os, subprocess, sys, shutil
from pathlib import Path
from export_all import scan, read, write, sha, FAMILIES
from datetime import datetime, timezone
from prediction_coverage import audit
from emulator_gate import inventory, training_issues

def queue(root):
    home=root/'Daily_Run_Reports/S3_Exports';index=home/'index.json'
    rows=[]
    for r in read(index)['rows']:
        row=dict(r);rows.append(row)
        if r['status']!='source_exported':continue
        bundle=(home/r['bundle']).resolve()
        if not bundle.is_relative_to(home.resolve()):raise ValueError('invalid export path')
        m,h=inventory(bundle);row['bundle_sha256']=h
        for name,(profile,_,report) in FAMILIES.items():
            if profile==r['profile']:
                p=home.parent/'Model_Experiments'/name/r['run']/report
                if sha(p)!=m['report_sha256']:raise ValueError('model report changed during queueing')
                row['training_warnings']=training_issues(read(p))
                mod=profile[:3];manifest=home.parent/'Training_Phase1'/('spectrogram_candidates.csv' if mod=='bmp' else 'wav_candidates.csv')
                archived=home/'Frozen_Manifests'/(m['dataset_sha256']+'.csv')
                report=audit(archived if archived.is_file() else manifest,m['dataset_sha256'],p.parent/'predictions.csv',mod)
                loc=home/'Prediction_Coverage'/profile/r['run']/(h+'.json')
                write(loc,report);row['prediction_coverage']=report['status'];row['prediction_report']=loc.relative_to(home).as_posix()
    payload=dict(schema=1,index_sha256=sha(index),rows=rows,promotion_ready=False)
    # Pin the requested index: the next Daily must not change an in-flight test.
    # Use normal index paths for resolution by the runner; copy at home level.
    snap=home/('queued_'+payload['index_sha256']+'.json')
    if not snap.exists():write(snap,read(index))
    if sha(snap)!=payload['index_sha256']:raise ValueError('queued index does not match')
    write(home/'queue.json',payload)
    return snap
def worker(root,snap,config):
    wsl=shutil.which('wsl.exe')
    if not wsl:raise ValueError('Windows Subsystem for Linux is required for this launcher')
    args=[wsl]+(['--distribution',config['distro']] if config.get('distro') else [])+['--exec']
    def path(p):return subprocess.check_output(args+['wslpath','-u',str(p)],encoding='utf-8').strip()
    cmd=args+['bash','-c','set -e; source "$1/export.sh" >/dev/null; exec python "$2" "$3" --emu "$4"','s3-worker',config['idf_dir'],path(root/'BatDailyTool/S3_Candidates/emulator_gate.py'),path(snap),config['emu']]
    log=snap.parent/'Emulator_worker.log'
    with log.open('ab') as f:subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=f,stderr=f,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('Emulator requested; worker log:',log)
def main(root,mode):
    root=root.resolve();cfg=root/'BatDailyTool/S3_Candidates/wsl_worker.local.json'
    if mode=='configure':
        settings=dict(distro=input('WSL distribution [default]: ').strip(),idf_dir=input('ESP-IDF directory in WSL (e.g. /home/bat/esp/esp-idf): ').strip(),emu=input('esp-emu executable in WSL (absolute path): ').strip())
        if not all(settings[k].startswith('/') for k in ('idf_dir','emu')):raise ValueError('Use absolute Linux paths')
        write(cfg,settings);mode='run'
    rc=scan(root) if mode=='export' else 0
    snap=queue(root)
    if cfg.is_file():worker(root,snap,read(cfg))
    elif mode=='run':raise ValueError('Configure the WSL worker first (or run emulator_gate.py natively in Linux)')
    else:print('S3 emulator queue refreshed; no WSL worker configured.')
    return rc
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',type=Path,required=True);a.add_argument('--mode',choices=['export','run','configure'],default='export');v=a.parse_args();sys.exit(main(v.root,v.mode))
