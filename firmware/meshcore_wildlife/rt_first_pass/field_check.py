"""Verify parent WAV ACK and linked candidate journal records on the running RT."""
from datetime import datetime
from pathlib import Path
import json
import os
import wave
import re
import time
import serial

def fields(line):
    return dict(re.findall(r'(\w+)=([^\s]+)',line))

def key(record,field):
    return (record['session'].lower(),record['run'],record[field])

def verify_receiver_clip(owner):
    session, run, seq = owner
    root = Path(os.environ.get('NZRT_BAT_ROOT', Path.home()/'Documents'/'Bat'))
    config = root/'bat_config.json'
    settings = json.loads(config.read_text(encoding='utf-8-sig')) if config.exists() else {}
    backup = root/Path(settings.get('receiver', {}).get('backup_root') or 'WiFi_Backup')
    pattern = f'*/????????/*_RT_{session}_{run}_{seq}.json'
    for path in (backup/'RT_Clips').glob(pattern):
        meta = json.loads(path.read_text())
        if (meta.get('firmware') != 'NZRT-J4-PASS-1' or meta.get('first_pass') != 'legacy'
                or meta.get('samples') != 384000 or meta.get('capture_valid') is not True):
            continue
        with wave.open(str(path.with_suffix('.wav')), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, 192000, 384000) and len(wav.readframes(384000)) == 768000:
                print('Verified continuous two-second WAV:', path.with_suffix('.wav'), flush=True)
                return True
    return False

def check(port,log):
    def command(s):
        port.write((s+'\r\n').encode())
        log.write('> '+s+'\n')
        log.flush()
    def read():
        line=port.readline().decode(errors='replace').strip()
        if line:
            log.write(line+'\n')
            log.flush()
        return line
    end=time.monotonic()+40
    next_query=0
    while time.monotonic()<end:
        if time.monotonic()>=next_query:
            command('nzrt status')
            next_query=time.monotonic()+4
        line=read()
        if 'NZRT DIAG build=NZRT-J4-PASS-1 ' in line:break
    else:raise RuntimeError('PASS-1 firmware identity unconfirmed on COM8.')
    links={}
    saved=set()
    ack=set()
    passed=False
    auto=False
    try:
        for s in ('nzrt test off','nzrt ml shadow','nzrt wav on','nzrt day test wake'):
            command(s)
            time.sleep(.25)
        for active,shadow in [('legacy','off'),('audible','legacy'),('evolved','legacy'),('legacy','evolved')]:
            command('nzrt pass '+active+' '+shadow)
            until=time.monotonic()+25
            first=None
            query=0
            while time.monotonic()<until:
                if time.monotonic()>=query:
                    command('nzrt pass status')
                    query=time.monotonic()+1
                line=read()
                if not line.startswith('NZRT FIRST_PASS version=PASS-1 '):continue
                rec=fields(line)
                if (rec.get('active'),rec.get('shadow'))!=(active,shadow):continue
                windows=int(rec['windows'])
                if first is None:first=windows
                if windows>first:break
            else:raise RuntimeError('Detector selection or advancing DSP unverified: '+active+' '+shadow)
        print('Verified live detector switches and advancing DSP windows.')
        print('Play the repeating tester now, for about 20 seconds. Waiting for a shared candidate and its parent WAV ACK.',flush=True)
        end=time.monotonic()+150
        while time.monotonic()<end:
            line=read()
            if not line.startswith('NZRT '):continue
            rec=fields(line)
            if line.startswith('NZRT CANDIDATE ') and rec.get('clip_request')=='shared':
                child=key(rec,'seq')
                owner=key(rec,'clip_owner_seq')
                if owner!=child and owner[2]!='0':links[child]=owner
            elif line.startswith('NZRT CANDIDATE_SAVED '):saved.add(key(rec,'seq'))
            elif line.startswith('NZRT WAV ') and rec.get('result')=='ACK':
                ack.add(key(rec,'seq'))
            for child,owner in links.items():
                if child in saved and owner in saved and owner in ack and verify_receiver_clip(owner):
                    print('Verified session %s run %s: candidate %s shared WAV %s; both journalled and parent ACK received.' % (*child,owner[2]))
                    passed=True
                    break
            if passed:break
    finally:
        command('nzrt pass legacy evolved')
        command('nzrt day auto')
        end=time.monotonic()+15
        next_query=0
        while time.monotonic()<end:
            if time.monotonic()>=next_query:
                command('nzrt day')
                next_query=time.monotonic()+3
            line=read()
            if line.startswith('NZRT DAY state='):
                print(line)
                f=fields(line)
                if f.get('mode')=='AUTO' and f.get('schedule_enabled')=='1' and f.get('clock')=='SYNCED':
                    auto=True
                    break
    if not passed:print('Sharing / delivery unverified during this window. See the log for armed, shared, busy and ACK entries.')
    if not auto:print('Automatic synced schedule unconfirmed. Check nzrt day before leaving.')
    return passed and auto

if __name__=='__main__':
    path=Path(__file__).with_name('RT_pass1_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.log')
    print('Writing',path,flush=True)
    with path.open('x',encoding='utf8') as log,serial.Serial('COM8',115200,timeout=.5) as port:
        raise SystemExit(0 if check(port,log) else 1)
