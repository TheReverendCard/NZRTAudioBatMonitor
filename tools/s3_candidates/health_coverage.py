"""Summarise the RT's own per-interval loss counters; never infer calls from silence."""
import argparse,re,zipfile
from pathlib import Path
from collections import Counter
from export_all import write
def audit(lines):
    seen={};conflicts=set();invalid=0
    for line in lines:
        idx=line.find('NZRT FIELD health=1 ')
        if idx<0:continue
        d=dict(re.findall(r'(\w+)=([^\s,"]+)',line[idx:]))
        try:
            k=(d['session'],int(d['run']),int(d['utc']))
            v=(d['state'],int(d['windows_delta']),int(d['dsp_drop_delta']),int(d['live_dropped']) if 'live_dropped' in d else None)
            if k[2]<=0 or min(v[1:3])<0:raise ValueError()
        except (ValueError,KeyError):invalid+=1;continue
        if k in seen and seen[k]!=v:conflicts.add(k)
        seen[k]=v
    totals=Counter();last={};out=[]
    for k,v in sorted(seen.items()):
        gap=k[2]-last[k[:2]] if k[:2] in last else None;last[k[:2]]=k[2]
        status='unknown' if k in conflicts else 'reported_gap' if v[0]=='GAPS' or v[2]>0 else 'observed' if v[0]=='MONITORING' and v[1]>0 else 'unknown'
        if gap and gap>90:totals['separations_over_90s']+=1
        totals[status]+=1
        if k not in conflicts:totals['reported_dsp_drop_delta_sum']+=v[2]
        out.append(dict(session=k[0],run=k[1],utc=k[2],status=status,windows_delta=v[1],dsp_drop_delta=v[2],live_dropped_value=v[3],seconds_since_previous=gap))
    return dict(totals=dict(totals),bad_rows=invalid,conflicts=len(conflicts),intervals=out,coverage='partial_observations' if out else 'unknown',inferred_missed_calls=None)
def lines(paths):
    for p in paths:
        if p.suffix.lower()=='.zip':
            with zipfile.ZipFile(p) as z:
                for i in z.infolist():
                    if i.filename.lower().endswith('.txt'):
                        with z.open(i) as f:yield from (x.decode('utf-8','replace') for x in f)
        else:
            with p.open(encoding='utf-8-sig',errors='replace') as f:yield from f
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('log',nargs='+',type=Path);a.add_argument('--out',required=True,type=Path);v=a.parse_args()
    report=audit(lines(v.log));write(v.out,report);print(report['coverage'],report['totals'],v.out)
