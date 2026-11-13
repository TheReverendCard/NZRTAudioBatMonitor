"""Run the installed GUARD-2 serial diagnostic; no flashing, model or WAV setting edits."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STAGES = ('capture', 'score', 'send')
BUILD = 'NZRT-J4-GUARD-2'

def fields(line):
    return dict(re.findall(r'\b(\w+)=([^\s]+)', line))

class Link:
    def __init__(self, port, out):
        self.port, self.out = port, out
        self.pending = bytearray()
        self.session = None

    def send(self, cmd):
        self.out.write('> ' + cmd + '\n')
        self.port.write((cmd+'\r\n').encode('ascii'))
        self.port.flush()

    def line(self, deadline):
        while time.monotonic() < deadline:
            end = self.pending.find(b'\n')
            if end >= 0:
                s = self.pending[:end].decode('utf8','replace').rstrip('\r')
                del self.pending[:end+1]
                self.out.write(s+'\n')
                if self.session and s.startswith(('NZRT ALIVE ', 'NZRT DIAG ', 'NZRT DAY_MODE ')):
                    session = fields(s).get('session')
                    if session and session.lower() != self.session:
                        raise RuntimeError('Board restarted; results from different sessions cannot be combined.')
                if s.startswith(('NZRT COMPARE ', 'NZRT TEST_AUDIO ', 'NZRT TEST bench=', 'NZRT HTTP route=/rt-test-clip ')):
                    print(s,flush=True)
                return s
            self.pending.extend(self.port.read(min(4096,self.port.in_waiting or 1)))
            if len(self.pending)>131072 and b'\n' not in self.pending:
                raise RuntimeError('No serial line endings received.')
        raise TimeoutError('Timed out waiting for a board response.')

def wait(link, prefix, seconds):
    limit = time.monotonic()+seconds
    while True:
        line = link.line(limit)
        if line.startswith(prefix): return fields(line)

def run_stage(link, stage, rec):
    cmd = 'nzrt compare '+stage
    accept_by = time.monotonic()+120
    while True:
        if time.monotonic() >= accept_by: raise TimeoutError('Board stayed busy before '+stage)
        link.send(cmd)
        # Retry only an explicit WAIT; silence is not authority to repeat a command.
        while True:
            line = link.line(accept_by)
            if line.startswith('NZRT COMPARE WAIT '):
                time.sleep(2); break
            if line.startswith('NZRT COMPARE UNAVAILABLE'):
                raise RuntimeError(line+' (check bench mode, NTP clock and diagnostic buffer)')
            if line.startswith('NZRT COMPARE START '):
                if fields(line).get('stage')!=stage: raise RuntimeError('Unexpected stage: '+line)
                return finish_stage(link,stage,rec)

def finish_stage(link,stage,rec):
    deadline = time.monotonic()+100
    armed = None
    ack = set()
    captured = {}
    while True:
        line=link.line(deadline); f=fields(line)
        if line.startswith('NZRT TEST session=') and f.get('session','').lower()==link.session and f.get('run')=='0' and f.get('source')=='manual':
            if f.get('result')=='ARMED': armed=f.get('seq')
            if f.get('result')=='ACK': ack.add(f.get('seq'))
        elif line.startswith('NZRT TEST_AUDIO '): captured[f.get('seq')]=f
        elif line.startswith('NZRT COMPARE '):
            if f.get('stage')!=stage: continue
            for kind in ('TIMING','COUNTERS','END'):
                if line.startswith('NZRT COMPARE '+kind+' '): rec[kind.lower()]=f
            if 'end' in rec: break
    if not {'timing','counters'}<=rec.keys(): raise RuntimeError(stage+': END without TIMING and COUNTERS')
    seq=rec['end'].get('seq')
    if not seq or seq=='0' or seq!=armed: raise RuntimeError(stage+': no matching diagnostic capture was armed')
    # Upload can occur after END. Guard the transition using the sequence and session;
    # an earlier candidate/journal ACK is never a diagnostic clip acknowledgement.
    deadline=time.monotonic()+120
    while seq not in ack:
        line=link.line(deadline);f=fields(line)
        if line.startswith('NZRT TEST_AUDIO '): captured[f.get('seq')]=f
        if (line.startswith('NZRT TEST session=') and f.get('session','').lower()==link.session
            and f.get('run')=='0' and f.get('source')=='manual' and f.get('result')=='ACK'):
            ack.add(f.get('seq'))
    rec.update(seq=seq,receiver_ack=True,audio=captured.get(seq))
    if rec['audio'] is None:raise RuntimeError(stage+': missing TEST_AUDIO line')

def execute(link,result):
    link.send('nzrt status')
    diag=wait(link,'NZRT DIAG ',20)
    if diag.get('build')!=BUILD or not diag.get('session'): raise RuntimeError('This runner requires '+BUILD)
    link.session=diag['session'].lower();result['session']=link.session
    link.send('nzrt test status')
    pre=wait(link,'NZRT TEST_STATUS ',12)
    if pre.get('period_s')!='0' or pre.get('bench')!='0' or pre.get('buffer')!='1':
        raise RuntimeError('Requires an idle bench, periodic off, and allocated diagnostic buffer. Existing settings left in place.')
    try:
        link.send('nzrt compare prepare')
        wait(link,'NZRT TEST bench=ON ',15)
        for name in STAGES:
            rec=result['stages'][name]={}
            run_stage(link,name,rec)
        result['measurements_complete']=True
    finally:
        link.send('nzrt compare stop')
        wait(link,'NZRT TEST bench=OFF ',10)
        result['automatic_schedule_restored']=True

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',default='COM8')
    p.add_argument('--output-root',type=Path,default=Path(os.getenv('NZRT_BAT_ROOT',Path.home()/'Documents'/'Bat'))/'Daily_Run_Reports'/'RT_Compare')
    a=p.parse_args()
    try: import serial
    except ImportError:
        print('Install pyserial:  py -3 -m pip install pyserial');return 2
    folder=a.output_root/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True,exist_ok=False)
    result={'status':'incomplete','stages':{},'measurements_complete':False,'automatic_schedule_restored':False}
    print('Receiver should be running. Results:',folder,flush=True)
    try:
        with (folder/'serial.txt').open('x',encoding='utf8',buffering=1) as log:
            with serial.Serial(port=None,baudrate=115200,timeout=.25,write_timeout=3) as port:
                port.dtr=False;port.rts=False;port.port=a.port;port.open()
                time.sleep(2);port.reset_input_buffer()
                execute(Link(port,log),result)
        result['status']='measurements_collected'
        print('Three measurements collected. Inspect COUNTERS for losses; completion does not mean zero drops.')
    except (OSError,RuntimeError,KeyboardInterrupt) as e:
        result['error']=str(e) or type(e).__name__
        print('Incomplete:',result['error'])
        if not result['automatic_schedule_restored']:
            print('If bench mode was started, send nzrt compare stop in miniterm when reconnected.')
    finally:
        (folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    return int(result['status']!='measurements_collected')

if __name__=='__main__': sys.exit(main())
