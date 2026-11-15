import argparse,tempfile,sys,shutil,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'payload'))
import acoustic_pairs as a
import numpy as np
def check(field):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);day='20261107';sd=root/day/('Xiao'+day);ar=root/day/('AR4'+day);sd.mkdir(parents=True);ar.mkdir()
        bmp=ar/'20261108_031059.bmp';shutil.copyfile(field/bmp.name,bmp)
        w=sd/'event_20261107T141237Z_00947.wav';shutil.copyfile(field/w.name,w);shutil.copyfile(field/(w.name+'.json'),Path(str(w)+'.json'))
        start=1794060757.295566
        ref=start-98.295566+14
        row=lambda p,rec,t,d:dict(source=p.relative_to(root).as_posix(),kind='event',recorder=rec,start=t,end=t+d,duration_seconds=d,clock_note='fixture')
        rows=[dict(row(bmp,'AR4',ref,7.632),human_level='confirmed'),row(w,'XIAO SD',start,5.119)]
        # Put real unrelated field clips at times closer to the nominal AR4 timestamp.
        for i,p in enumerate(sorted(field.glob('*.wav'))):
            if p.name==w.name:continue
            target=sd/p.name;shutil.copyfile(p,target);rows.append(row(target,'XIAO SD',ref+i,5))
        r=a.night(root,day,rows,{'ar4_clock_adjust_seconds':14});e=r['records'][0];print('WAVs',len(e['tested']),e['status'],[(v['wav'],v['score']) for v in e['candidates']])
        if e['issues']:
            assert e['status']=='incomplete search'
            for issue in e['issues']:
                src=issue.split(': ',1)[0];(root/src).unlink();rows=[rr for rr in rows if rr['source']!=src]
            r=a.night(root,day,rows,{'ar4_clock_adjust_seconds':14});e=r['records'][0];print('Readable pool',len(e['tested']),e['status'])
        assert e['status']=='probable shared pass' and e['candidates'][0]['wav'].endswith(w.name)
        z=e['candidates'][0];assert abs(z['lag_s']-2.814)<.01 and abs(z['total_clock_correction_s']-95.48)<.1
        assert not r['anchors_and_clock_segments'][0]['usable']
        a.publish_night(root,r);a.index(root)
        copy=sd/'duplicate.wav';shutil.copyfile(w,copy);rows.append(row(copy,'XIAO SD',ref,5))
        assert a.night(root,day,rows,{'ar4_clock_adjust_seconds':14})['records'][0]['status']=='ambiguous'
        assert a.assessment([])=='no convincing match'
        print('PASS field retrieval, provisional clock, ambiguous duplicate and rendered review')
def clocks():
    records=[dict(status='probable shared pass',ar4_utc=t,candidates=[dict(wav=str(t),residual_s=r)]) for t,r in [(0,80),(1200,80.5),(2400,81),(3600,-20)]]
    g=a.clock_groups(records);assert len(g)==2 and g[0]['usable'] and abs(g[0]['drift_s_per_hour']-1.5)<1e-6 and not g[1]['usable']
    assert a.rt_outcome({'sd_utc':100,'pulse_times_sd_s':[0,2]},[dict(id='s:2:1',recorder='XIAO RT',kind='candidate',start=28,end=28.02)])['rt_triggers']==[]
    print('PASS clock drift/jump and distant RT event exclusion')
if __name__=='__main__':
    clocks();p=argparse.ArgumentParser();p.add_argument('field',type=Path);check(p.parse_args().field)
