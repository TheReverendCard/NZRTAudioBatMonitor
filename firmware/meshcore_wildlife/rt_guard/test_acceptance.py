from bench_acceptance import gate
def good():
 s=['NZRT DIAG build=NZRT-J4-GUARD-1 session=AA','NZRT EVENT_BUFFER ram_dropped_oldest=0 flash_write_failures=0','NZRT SCORE event_queue_lost=0']
 for i in range(31):
  s.append(f'NZRT MIC session=AA mode=MONITORING capture=ON t={i*60}s dsp_done={i+1} dsp_drop=0 dsp_gap=0 short=0 errors=0 legacy_rx_q_ovf=1')
  if i%5==0:s.append(f'NZRT FIELD health=1 session=AA run=1 utc={1800000000+i*60} state=MONITORING windows_delta=2999 dsp_drop_delta=0 live_dropped=0 guard_online=1 guard_fault=0 safe=0')
 for k,suffix in [('CANDIDATE','clip_request=armed'),('CANDIDATE_SAVED',''),('WAV','result=ACK')]:s.append(f'NZRT {k} session=aa run=1 seq=8 {suffix}')
 return '\n'.join(s)
s=good()
assert gate(s)['status']=='bench_transcript_passed'
for bad in ['',s.replace('result=ACK','result=FAILED'),s.replace('dsp_drop_delta=0','dsp_drop_delta=1'),s.replace('guard_online=1','guard_online=0'),s.replace('session=aa','session=ff'),s.replace('t=900s','t=2000s'),s.replace('windows_delta=2999','windows_delta=0')]:
 assert gate(bad)['status']=='needs_attention'
print('PASS deployment transcript rejects absent progress, gaps, missing supervisor and unrelated ACKs')
