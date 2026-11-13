"""Read one continuous serial transcript from a GUARD-1 monitored playback bench.
Refuse silence, restarts, unreported gaps, lost metadata or uncorroborated delivery.
"""
import argparse,json,re,sys
from pathlib import Path
def gate(text,mins=30):
 seen=set();health={};saved=set();events=set();acked=set();mic=[];sessions=set();flags=set();guard=False
 for line in text.splitlines():
  if not line.startswith('NZRT '):continue
  r=dict(re.findall(r'(\w+)=([^\s]+)',line))
  if line.startswith('NZRT DIAG '):
   if r.get('build')!='NZRT-J4-GUARD-1':flags.add('unexpected_build')
   else:seen.add('build');sessions.add(r.get('session'))
  if line.startswith('NZRT FIELD health=1 '):
   if 'utc' not in r or int(r['utc'])<1760000000:flags.add('unsynced_health');continue
   k=(r.get('session'),r.get('run'),int(r['utc']))
   if k in health and r!=health[k]:flags.add('conflicting_health')
   health[k]=r
   if r.get('guard_online')!='1' or r.get('guard_fault')!='0' or r.get('safe')!='0':flags.add('guard_fault_or_unavailable')
   if r.get('state')!='MONITORING' or int(r.get('windows_delta','0'))<=0 or r.get('dsp_drop_delta')!='0':flags.add('capture_gap_or_stall')
   if int(r.get('live_dropped','-1'))!=0:flags.add('live_queue_loss')
  if line.startswith('NZRT MIC ') and 'dsp_done' in r and r.get('mode')=='MONITORING' and r.get('capture')=='ON':
   mic.append((r.get('session'),int(r['t'].rstrip('s')),tuple(int(r[k]) for k in ('errors','short','dsp_drop','dsp_gap','legacy_rx_q_ovf','dsp_done'))))
  if line.startswith('NZRT SCORE ') and 'event_queue_lost' in r:
   seen.add('score');flags.update(['detector_events_lost'] if r['event_queue_lost']!='0' else [])
  if line.startswith('NZRT EVENT_BUFFER '):
   seen.add('buffer');flags.update(['pending_events_lost'] if r.get('ram_dropped_oldest')!='0' or r.get('flash_write_failures')!='0' else [])
  if (line.startswith('NZRT CANDIDATE ') or line.startswith('NZRT WAV ') or line.startswith('NZRT CANDIDATE_SAVED ')) and all(k in r for k in ('session','run','seq')):
   key=(r['session'].lower(),r['run'],r['seq'])
   if line.startswith('NZRT WAV ') and r.get('result')=='ACK':acked.add(key)
   if line.startswith('NZRT CANDIDATE_SAVED '):saved.add(key)
   if line.startswith('NZRT CANDIDATE ') and r.get('clip_request')=='armed':events.add(key)
 if seen!={'build','score','buffer'}:flags.add('missing_status_or_queue_evidence')
 segments={(k[0],k[1]) for k in health}
 if len(segments)!=1 or len(sessions)!=1 or {k[0] for k in segments}!=sessions:flags.add('missing_or_mixed_session_run')
 times=sorted(set(k[2] for k in health))
 if not times or times[-1]-times[0]<60*mins or any(b-a>365 for a,b in zip(times,times[1:])):flags.add('insufficient_health_coverage')
 if len(mic)<2 or mic[-1][1]-mic[0][1]<mins*60:flags.add('insufficient_mic_coverage')
 for (s,a,ca),(t,b,cb) in zip(mic,mic[1:]):
  if s!=t or s not in sessions or not 0<b-a<=90 or ca[:-1]!=cb[:-1] or cb[-1]<=ca[-1]:flags.add('missing_audio_or_mic_error')
 if not any(k[0] in {str(x).lower() for x in sessions} and k[1] in {v for _,v in segments} for k in events&saved&acked):flags.add('no_correlated_recording_journal_ack')
 return {'status':'needs_attention' if flags else 'bench_transcript_passed','findings':sorted(flags),'minimum_minutes':mins,'production_approved':False}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('serial_log',type=Path);v=a.parse_args()
 try:r=gate(v.serial_log.read_text(errors='replace'))
 except (ValueError,KeyError) as exc:r={'status':'needs_attention','findings':['malformed telemetry: '+str(exc)]}
 print(json.dumps(r,indent=2));sys.exit(int(r['status']!='bench_transcript_passed'))
