"""Summarise new ML journal records without altering Daily Run or existing logs."""
import csv,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
FIELDS=re.compile(r'([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)')
def main():
 cfg=ROOT/'bat_config.json';c=json.loads(cfg.read_text(encoding='utf-8-sig')) if cfg.exists() else {}
 root=Path(c.get('receiver',{}).get('backup_root',str(ROOT/'WiFi_Backup')))/'RT';records={}
 for path in root.rglob('*.txt'):
  for line in path.read_text(encoding='utf-8',errors='replace').splitlines():
   if not line.startswith('NZRT ML '):continue
   fields=dict(FIELDS.findall(line));fields['source_file']=str(path)
   key=tuple(fields.get(k,'') for k in ['session','run','seq','model','mode']);records[key]=fields
 out=ROOT/'RT_ML_Review';out.mkdir(parents=True,exist_ok=True)
 rows=sorted(records.values(),key=lambda r:(int(r.get('utc_start','0')),r.get('session',''),int(r.get('seq','0'))))
 names=['session','run','seq','utc_start','model','mode','probability','threshold','valid','decision','inference_us','samples','sample_rate','clip_policy','source_file']
 with (out/'RT_ML_All.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=names,extrasaction='ignore');w.writeheader();w.writerows(rows)
 summary={'unique_scored_clips':len(rows),'valid':sum(r.get('valid')=='1' for r in rows),'bat_candidates':sum(r.get('valid')=='1' and r.get('decision')=='bat_candidate' for r in rows),'note':'Predictions are unreviewed. Overlapping receiver snapshots deduplicated by session/run/seq/model/mode. Skipped-buffer counts are in ML_STATUS and are not scored negatives.'}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2));print(out/'RT_ML_All.csv')
if __name__=='__main__':main()
