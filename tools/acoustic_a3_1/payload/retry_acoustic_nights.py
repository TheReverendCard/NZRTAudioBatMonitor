"""Rebuild selected acoustic reports under a single lock. Log any per-night traceback."""
import argparse,contextlib,sys,traceback
from pathlib import Path
from datetime import datetime,timezone
import acoustic_pairs as ap
import daily_timeline as d
import rt_logs,bat_tool
from run_integrity import run_lock
def main():
    parser=argparse.ArgumentParser();parser.add_argument('nights',nargs='+');args=parser.parse_args()
    here=Path(__file__).resolve().parent;root=here.parent
    with run_lock(root,'retry acoustic pairing'):
        dest=root/'Daily_Run_Reports'/'Acoustic_Retries';dest.mkdir(parents=True,exist_ok=True)
        log=dest/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.log')
        print('Retry log:',log,flush=True)
        cfg={**bat_tool.DEFAULTS,**(bat_tool.read_json(here/'config.json') or {})}
        days=set(d.report_days(root));parsed=rt_logs.load_archives(root);failed=[]
        with log.open('x',encoding='utf8') as f:
            def say(message):
                print(message,flush=True);print(message,file=f,flush=True)
            for night in dict.fromkeys(args.nights):
                say('Checking '+night)
                try:
                    if night not in days:raise ValueError('No canonical recorder night '+night)
                    info=d.session_info(root,night);rows,warnings=d.source_rows(root,night,cfg,info);lo,hi=info['window']
                    for key,kind in [('events','candidate'),('ml','MLP result')]:
                        rows.extend(dict(r,recorder='XIAO RT',kind=kind) for r in parsed.get(key,[]) if lo<=r['start']<hi)
                    report=ap.night(root,night,rows,{**cfg,**cfg.get('days',{}).get(night,{})});report['source_warnings']=warnings
                    ap.publish_night(root,report)
                    say(night+': report written; '+str(len(report['records']))+' reviewed AR4 recordings')
                except Exception as e:
                    failed.append(night);say(night+': FAILED: '+str(e));traceback.print_exc(file=f);f.flush()
            ap.index(root)
            say('Still needing attention: '+(', '.join(failed) or 'none'))
        return int(bool(failed))
if __name__=='__main__':sys.exit(main())
