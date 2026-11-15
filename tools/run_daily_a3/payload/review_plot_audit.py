"""Compare canonical explicit grades to the rebuilt per-recording timeline; never change them."""
import json
from pathlib import Path
from collections import Counter
import annotation_care as care
def audit(root,days):
    results={};mismatches=[]
    for day in days:
        data=care.read_json(root/'Daily_Timeline'/day/'timeline.json',{})
        rows={}
        for r in data.get('events',[]):
            src=Path(r['source'])
            if r['recorder']=='XIAO SD':src=src.with_suffix('.bmp')
            rows[src.as_posix()]=r
        grades=Counter();plotted=Counter()
        for prefix in ('AR4','Xiao','XiaoRT'):
            for p in (root/day/(prefix+day)).glob('*.bmp.data'):
                try:
                    hdr=json.loads(p.read_text(encoding='utf-8-sig'))[0]
                    g=hdr.get('BatDailyReview',{}).get('grade')
                    if type(g) is not int or not 1<=g<=5:continue
                    rel=p.with_suffix('').relative_to(root).as_posix();grades[g]+=1
                    row=rows.get(rel,{})
                    if row.get('human_grade')==g:plotted[g]+=1
                    else:mismatches.append(dict(source=rel,grade=g,timeline_grade=row.get('human_grade'),reason=row.get('human_review_provenance','recording absent from timeline')))
                except (ValueError,IndexError,KeyError,AttributeError,OSError,TypeError) as e:mismatches.append(dict(source=str(p.relative_to(root)),reason=str(e)))
        results[day]=dict(canonical_grades=dict(grades),timeline_grades=dict(plotted))
    out=root/'Daily_Run_Reports'/'Review_Plot_Audit'/'latest.json'
    care.write_json(out,dict(days=results,mismatches=mismatches,scope='Explicit canonical grades only. Copies in third-party/staging folders do not establish a canonical grade.'))
    print('Review-to-plot audit:',len(mismatches),'mismatches;',out)
    return len(mismatches)
