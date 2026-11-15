"""Run after the existing daily launcher and its review windows have closed."""
from pathlib import Path
import sys
from run_integrity import run_lock
def main():
    import bat_tool, daily_timeline, daily_pipeline,rt_audio_daily
    from review_unreviewed_queue import ReviewQueue
    here=Path(__file__).resolve().parent;root=here.parent
    with run_lock(root,'final review reconciliation'):
        errors=[];q=ReviewQueue(root)
        try:
            saved=q.sync(abort_on_conflict=False)
            print('Fast Review: saved',saved['completed'],'staged grades;',len(saved['conflicts']),'conflicts;',saved['remaining'],'staged items remain.')
            errors+=['Queue conflict: '+str(x) for x in saved['conflicts']]
        except Exception as e:errors.append('Review sync: '+str(e))
        try:
            errors.extend(rt_audio_daily.classify_received(root,bat_tool.read_json(daily_pipeline.AUTO,{})))
        except Exception as e:errors.append('RT audio intake: '+str(e))
        cfg={**bat_tool.DEFAULTS,**(bat_tool.read_json(here/'config.json') or {})}
        days=daily_timeline.report_days(root)
        if not days:raise RuntimeError('No recorder dates; existing reports retained.')
        daily_timeline.refresh(root,cfg,days)
        from review_plot_audit import audit
        if audit(root,days):errors.append('Grade/report mismatch: see Review_Plot_Audit/latest.json')
        import json
        for day in days[-3:]:
            meta=json.loads((root/'Daily_Timeline'/day/'timeline.json').read_text())['metadata']
            print('Rebuilt',day,': human markers',meta['human_review_counts'],'; review states',meta['review_states'])
            if meta.get('review_states') and not any(meta['review_states'].get(k) for k in ('reviewed_metadata','reviewed_confirmed')):
                print('No accepted grades beside recordings for',day,'; check which folder Fast AviaNZ saved to.')
        q.backlog('After final review reconciliation')
        for e in errors:print('NEEDS ATTENTION:',e)
        return int(bool(errors))
if __name__=='__main__':sys.exit(main())
