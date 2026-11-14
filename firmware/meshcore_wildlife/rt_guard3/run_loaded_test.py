"""Four real-scoring/candidate-upload load phases; no flash, erase or model changes."""
import argparse,json,os,statistics,sys,time
from datetime import datetime,timezone
from pathlib import Path
from serial_link import Link,fields,wait
BUILD='NZRT-J5-GUARD-3'

def work(link):
 link.send('nzrt load status');return wait(link,'NZRT WORK ',15)
def journal(link):
 link.send('nzrt health status');return wait(link,'NZRT JOURNAL_RAM ',15)
def collect(link,seconds,rec):
 until=time.monotonic()+seconds
 while time.monotonic()<until:
  try:line=link.line(until)
  except TimeoutError:break
  record(line,rec)
def record(line,rec):
 for prefix,key in [('NZRT LOAD_ML ','scores'),('NZRT LOAD_WAV ','uploads'),('NZRT COMPARE TIMING ','timing'),('NZRT COMPARE COUNTERS ','counters')]:
  if line.startswith(prefix):
   f=fields(line)
   if key in ('timing','counters'):rec[key]=f
   else:rec.setdefault(key,[]).append(f)

def assess(rec):
 errors=[];c=rec.get('counters',{})
 if not c:errors.append('Missing acquisition counters')
 for k in ('drops','gaps','dma_ovf','read_errors','short_reads'):
  if k not in c or int(c[k]):errors.append('Audio loss/error: '+k)
 if not c or min(int(c.get('blocks',0)),int(c.get('done',0)))<100:errors.append('Insufficient audio processing progress')
 if abs(int(c.get('blocks',0))-int(c.get('done',0)))>48:errors.append('Received/processed difference exceeds buffer capacity')
 if int(rec['journal_after']['errors'])>int(rec['journal_before']['errors']):errors.append('New journal errors')
 if rec['journal_after'].get('circuit')=='1':errors.append('Journal circuit open')
 probes=int(rec['work_after']['probes'])-int(rec['work_before']['probes'])
 busy=int(rec['work_after']['probe_busy'])-int(rec['work_before']['probe_busy'])
 if probes<3:errors.append('Insufficient forced captures')
 if busy:errors.append(f'{busy} forced captures could not obtain a clip buffer')
 scores={s['seq']:s for s in rec.get('scores',[])}
 if len(scores)!=probes-busy:errors.append('Missing forced-capture score/skip results')
 if rec['inference'] and any(s.get('valid')!='1' or s.get('score_reason')!='complete' for s in scores.values()):errors.append('Inference skipped or invalid')
 if rec['wav']:
  ack={s['seq'] for s in rec.get('uploads',[]) if s.get('result')=='ACK'}
  if not scores.keys()<=ack:errors.append('Missing matched WAV acknowledgement')
 valid=[int(s['inference_us'])/1e6 for s in scores.values() if s.get('valid')=='1']
 rec['checks']={'pass':not errors,'issues':errors,'probes':probes,'busy':busy,'valid_scores':len(valid),'median_score_seconds':statistics.median(valid) if valid else None}
 return not errors

def execute(link,result,seconds):
 link.send('nzrt status');d=wait(link,'NZRT DIAG ',20)
 if d.get('build')!=BUILD:raise RuntimeError('Requires '+BUILD+'; device unchanged.')
 link.session=d['session'].lower();result['session']=link.session
 before=work(link);result['before']=before
 if before.get('load')!='0' or before.get('bench')!='0' or before.get('period_s')!='0' or before.get('idle')!='1':raise RuntimeError('Needs idle normal mode, bench and periodic off; existing test left untouched.')
 started=False
 try:
  started=True # stop also handles a START reply lost on serial
  link.send('nzrt load start');wait(link,'NZRT LOAD started=1 ',15)
  for infer,wav in [(0,0),(0,1),(1,0),(1,1)]:
   name=f'load{infer}{wav}';rec=result['phases'][name]={'inference':infer,'wav':wav,'scores':[],'uploads':[]}
   rec['work_before']=work(link);rec['journal_before']=journal(link)
   link.send(f'nzrt load phase {infer} {wav}');reply=wait(link,'NZRT LOAD phase=',15)
   if reply.get('phase')!=name:raise RuntimeError('Wrong phase acknowledged')
   collect(link,seconds,rec)
   link.send('nzrt load pause');deadline=time.monotonic()+360;next_status=0;idle=False
   while time.monotonic()<deadline:
    if time.monotonic()>=next_status:link.send('nzrt load status');next_status=time.monotonic()+5
    line=link.line(deadline);record(line,rec)
    if line.startswith('NZRT WORK ') and fields(line).get('idle')=='1':idle=True;break
   if not idle:raise RuntimeError('Pending clip work did not drain; phase incomplete')
   link.send('nzrt load finish');deadline=time.monotonic()+20
   while True:
    line=link.line(deadline);record(line,rec)
    if line.startswith('NZRT LOAD finished=1'):break
   rec['work_after']=work(link);rec['journal_after']=journal(link)
   assess(rec)
  result['measurements_complete']=True
 finally:
  if started:
   link.send('nzrt load stop');wait(link,'NZRT LOAD stopped=1 ',15)
   after=work(link);result['after']=after
   result['settings_restored']=all(after.get(k)==before.get(k) for k in ('inference','wav','mode')) and after.get('bench')=='0' and after.get('load')=='0'
   if not result['settings_restored']:raise RuntimeError('Restoration not verified; inspect before/after settings')
 result['qualification_pass']=all(r['checks']['pass'] for r in result['phases'].values())

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port');p.add_argument('--seconds',type=int,default=300);p.add_argument('--output-root',type=Path,default=Path(os.getenv('NZRT_BAT_ROOT',Path.home()/'Documents'/'Bat'))/'Daily_Run_Reports'/'RT_GUARD3_Load');a=p.parse_args()
 if not 30<=a.seconds<=600:raise ValueError('Phase duration must be 30..600 seconds; default 300.')
 import serial
 from serial.tools import list_ports
 for port in list_ports.comports():print(port.device,port.description)
 name=a.port or input('RT COM port (close Serial Monitors): ').strip()
 if name.isdigit():name='COM'+name
 out=a.output_root/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,exist_ok=False)
 result={'build':BUILD,'phases':{},'settings_restored':False,'measurements_complete':False,'qualification_pass':False,'phase_seconds':a.seconds}
 print('Keep receiver running. Approximately 20–25 minutes at defaults. Results:',out,flush=True)
 try:
  with (out/'serial.txt').open('x',encoding='utf8',buffering=1) as log:
   with serial.Serial(port=None,baudrate=115200,timeout=.25,write_timeout=3) as ser:
    ser.dtr=False;ser.rts=False;ser.port=name;ser.open();time.sleep(2);ser.reset_input_buffer()
    execute(Link(ser,log),result,a.seconds)
 except (Exception,KeyboardInterrupt) as e:result['error']=str(e) or type(e).__name__;print('Incomplete:',result['error'])
 finally:
  (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
 print('PASS' if result['qualification_pass'] else 'NEEDS ATTENTION. Read summary.json; completion alone is not a pass.')
 if not result['settings_restored']:print('Restore after reconnecting with: nzrt load stop. Board has a one-hour automatic test expiry.')
 print('Return serial.txt and summary.json from:',out)
 return int(not result['qualification_pass'])
if __name__=='__main__':sys.exit(main())
