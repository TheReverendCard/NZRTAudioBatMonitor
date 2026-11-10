"""Exercise this RT over USB, matching candidate IDs to journal and receiver evidence."""
import argparse
import json
import re
import time
import hashlib
from datetime import datetime
from pathlib import Path


def fields(line):
    return dict(re.findall(r'(\w+)=([^\s]+)', line))


def identity(values):
    return (values.get('session', '').upper(), values.get('run'), values.get('seq'))


def check(lines, receiver, started):
    candidates, saved, received, clips = set(), set(), set(), set()
    blocks, window_deltas = [], []
    build = False
    sessions = set()
    active_windows = []
    active_session = None
    health_bad = False
    for line in lines:
        v = fields(line)
        if line.startswith('NZRT DIAG '):
            build |= v.get('build') == 'NZRT-J4-LIVE-1'
        if line.startswith('NZRT CANDIDATE '):
            candidates.add(identity(v))
        if line.startswith('NZRT CANDIDATE_SAVED '):
            saved.add(identity(v))
        if line.startswith('NZRT MIC '):
            active_session = v.get('session') if v.get('mode') == 'MONITORING' else None
        if line.startswith('NZRT BAND session=') and v.get('session') == active_session:
            active_windows.append(int(v['windows']))
        if line.startswith('NZRT MIC ') and v.get('mode') == 'MONITORING' and 'dsp_done' in v:
            blocks.append(v)
            sessions.add(v.get('session'))
        if line.startswith('NZRT FIELD health=1 '):
            health_bad |= v.get('state') in {'STALLED', 'GAPS', 'MIC_INIT_FAILED'}
            if 'windows_delta' in v:
                window_deltas.append(int(v['windows_delta']))
        if line.startswith('NZRT WAV ') and v.get('result') == 'ACK':
            clips.add(identity(v))
    if receiver.is_dir():
        for meta in (receiver/'RT').glob('*/*.json'):
            if meta.stat().st_mtime < started-2:
                continue
            try:
                m=json.loads(meta.read_text(encoding='utf-8-sig'))
                if m.get('firmware')!='NZRT-J4-LIVE-1' or not m.get('complete'):
                    continue
                body=meta.with_suffix('.txt').read_bytes()
                if hashlib.sha256(body).hexdigest()!=m.get('sha256'):
                    continue
                records=body.decode().splitlines()
                if all(x.startswith(('NZRT FIELD health=1 ','NZRT CANDIDATE ')) for x in records):
                    received.update(identity(fields(x)) for x in records if x.startswith('NZRT CANDIDATE '))
            except (ValueError, OSError):
                continue
    matched=candidates & saved & received
    print('Candidate IDs detected / journal-verified / received / matched:',
          len(candidates),len(saved),len(received),len(matched))
    for match in sorted(matched)[:5]:
        print('MATCH session=%s run=%s seq=%s' % match)
    print('Matched candidates with WAV ACK:',len(matched & clips))
    clean=False
    if len(blocks)>=2 and len(sessions)==1:
        first,last=blocks[0],blocks[-1]
        differences={k:int(last[k])-int(first[k]) for k in
                     ('dsp_done','dsp_drop','dsp_gap','errors','legacy_rx_q_ovf')}
        print('Active sample counter changes:',differences)
        elapsed=int(last['t'].rstrip('s'))-int(first['t'].rstrip('s'))
        rates=[int(b['bps']) for b in blocks[1:]]
        coverage=(active_windows[-1]-active_windows[0])/(50.0*elapsed) if elapsed>0 and len(active_windows)>=2 else 0
        print(f'Acoustic window coverage: {coverage:.1%}. Raw byte rates: {rates}')
        clean=(coverage>=0.95 and all(364800<=rate<=403200 for rate in rates)
               and differences['dsp_done']>0 and all(differences[k]==0 for k in differences if k!='dsp_done')
               and len(active_windows)>=2 and all(b>a for a,b in zip(active_windows,active_windows[1:]))
               and all(w>0 for w in window_deltas) and not health_bad)
    print('Continuous acquisition:', 'PASS' if clean else 'UNVERIFIED OR DEGRADED')
    return bool(build and clean and matched)


def main():
    import serial
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port',default='COM8')
    ap.add_argument('--receiver',type=Path,default=Path.home()/'Documents/Bat/WiFi_Backup')
    ap.add_argument('--seconds',type=int,default=210)
    args=ap.parse_args()
    if args.seconds<130:
        ap.error('At least 130 seconds are needed for two active minute reports')
    log=Path.cwd()/datetime.now().strftime('RT_field_%Y%m%d_%H%M%S.log')
    lines=[]
    started=time.time()
    deadline=time.monotonic()+25
    while True:
        try:
            connection=serial.Serial(args.port,115200,timeout=.5)
            break
        except serial.SerialException:
            if time.monotonic()>=deadline:
                raise
            time.sleep(1)
    with connection as port,log.open('x',encoding='utf-8') as out:
        def command(cmd):
            port.write((cmd+'\r\n').encode())
        finish=time.monotonic()+args.seconds
        wake=0
        try:
            while time.monotonic()<finish:
                if time.monotonic()>=wake:
                    command('nzrt day test wake')
                    command('nzrt status')
                    wake=time.monotonic()+50
                line=port.readline().decode(errors='replace').strip()
                if line:
                    print(line,flush=True)
                    out.write(line+'\n')
                    out.flush()
                    lines.append(line)
        finally:
            command('nzrt day auto')
    print('Serial log:',log)
    print('Receiver:',args.receiver)
    passed=check(lines,args.receiver,started)
    print('DETECT / LOG / REPORT:', 'PASS' if passed else 'NOT VERIFIED')
    return 0 if passed else 1

if __name__=='__main__':
    raise SystemExit(main())
