"""Install/restore review-first wiring without replacing local project modules wholesale."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

HERE=Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as tmp:
        tmp.write(data)
    os.replace(tmp.name,path)


def change(text,before,after):
    if text.count(before)!=1:
        raise ValueError("Installed source differs at: "+before[:100])
    return text.replace(before,after)


def acoustic_patch(src):
    a="try: ar.append({'file':rel(root,p),**bmp_info(p,cfg),**ar4_bat_evidence(p)})"
    b="try: wavs.append({'file':rel(root,p),**wav_info(p),**ar4_bat_evidence(p.with_suffix('.bmp'))})"
    for original,expr in ((a,"p"),(b,"p.with_suffix('.bmp')")):
        src=change(src,original,
            "if ar4_bat_evidence("+expr+").get('human_grade') not in (4,5):\n                    continue\n                "+original)
    return src


def gui_patch(src):
    marker="    gui=AviaNZ_manual.AviaNZ(configdir=configdir,firstFile=str(first_file))"
    return change(src,marker,'''    if os.environ.get("BAT_REVIEW_FIRST") == "1":
        # Session defaults on blank metadata, including the very first file.
        # Never stamp an annotation simply because it entered the queue.
        def session_field(key, default):
            def get(instance):
                return instance.__dict__.get(key, default)
            def set_value(instance, value):
                instance.__dict__[key] = (value or default) if key in instance.__dict__ else default
            return property(get, set_value)
        AviaNZ_manual.AviaNZ.reviewer = session_field("reviewer", "Jesse Card - Untrained")
        AviaNZ_manual.AviaNZ.operator = session_field("operator", "Auto")
'''+marker)



def summary_patch(src):
    src=change(src,"def update_summary(root,cfg):","def update_summary(root,cfg,changed=None,excluded=()):")
    src=change(src,"    for day,recorder,route,bmp in sources(root):",'''    if changed is None:
        inputs=sources(root)
        affected=None
    else:
        from review_first_daily import bmp_for
        paths={bmp_for(root/name) for name in changed}
        affected={p.relative_to(root).as_posix()+'.data' for p in paths}
        inputs=[]
        for bmp in sorted(paths):
            parts=bmp.relative_to(root).parts
            if len(parts)!=3 or not bmp.is_file():continue
            if re.fullmatch(r'ar4\\d{8}',parts[1],re.I):
                inputs.append((parts[0],parts[1],'AR4 standard',bmp))
            elif re.fullmatch(r'xiao\\d{8}',parts[1],re.I):
                inputs.append((parts[0],'XIAO','XIAO experimental',bmp))
    for day,recorder,route,bmp in inputs:
        if bmp.relative_to(root).as_posix() in excluded:continue''')
    return change(src,"if key not in seen:entry['status']='source_missing'","if key not in seen and (affected is None or key in affected):entry['status']='source_missing'")


def inventory_patch(src):
    start=src.index("    out=[];errors=[]",src.index("def build(root):"))
    end=src.index("    report_dir=",start)
    normal=src[start:end]
    return src[:start]+'''    import os,sys
    if os.environ.get("BAT_DAILY_INDEXED_REPORTS")=="1":
        from daily_reports import ReportCache
        cache=ReportCache(root)
        try:out,errors,legacy_stats=cache.inventory_rows(sys.modules[__name__],root,ledger)
        finally:cache.db.close()
    else:
'''+''.join('    '+line for line in normal.splitlines(True))+src[end:]


def post_patch(src):
    return change(src,'        write_json(logs / "summary.json", status)','        # Stage logs and the SQLite timing journal retain run history.')


def verified_patch(src):
    marker="    for iterator in (_canonical(root),_external_south(root)):"
    src=change(src,marker,'''    cache=None
    if os.environ.get("BAT_DAILY_INDEXED_REPORTS")=="1":
        from daily_reports import ReportCache
        cache=ReportCache(root)
    for iterator in (cache.verified_sources() if cache else _canonical(root),_external_south(root)):''')
    src=change(src,"                p=bmp.resolve()","                p=bmp if cache and site=='Shed' else bmp.resolve()")
    src=change(src,"                a=load_annotation(side)",'''                sig=cache.parts(bmp) if cache and site=="Shed" else None
                a=cache.fact("verified-label",bmp,sig,lambda:load_annotation(side)) if sig is not None else load_annotation(side)''')
    src=change(src,"                media_hash=hashlib.sha256(bmp.read_bytes()).hexdigest()",'''                def hash_bmp():return hashlib.sha256(bmp.read_bytes()).hexdigest()
                media_hash=cache.fact("digest",bmp,sig[0],hash_bmp) if sig is not None else hash_bmp()''')
    src=change(src,"    for key,item in same_media.items():","    if cache:\n        cache.db.commit()\n        cache.db.close()\n    for key,item in same_media.items():")
    src=change(src,"    dates=set()\n",'''    if os.environ.get("BAT_DAILY_INDEXED_REPORTS")=="1":
        from daily_reports import ReportCache
        cache=ReportCache(root)
        try:
            nights={p.split("/")[0] for p in cache.files if p.count("/")==2 and p.lower().endswith((".wav",".bmp"))}
            today=datetime.now(NZ).date()
            return {today.isoformat()} | {datetime.strptime(d,"%Y%m%d").date().isoformat() for d in nights if d.isdigit() and len(d)==8 and d<=today.strftime("%Y%m%d")}
        finally:cache.db.close()
    dates=set()
''')
    src=change(src,"let dates=DATA.agg.nights","let dates=[...DATA.agg.nights].reverse()")
    src=change(src,"Run Daily never launches performance evaluation.","See the nightly model trials for field predictions.")
    return src

def experimental_patch(src):
    src=change(src,"def collect(day):","def collect(day,excluded=()):")
    src=change(src,"    for p in sorted(day.glob('*.bmp.data')):","    for p in sorted(day.glob('*.bmp.data')):\n        if p.with_suffix('').relative_to(day.parent.parent).as_posix() in excluded:\n            found.pop(p.name,None)\n            continue")
    src=change(src,"def sync(root,core):","def sync(root,core,days=None,excluded=()):")
    src=change(src,"    for p in (root/'Matched/Pairs').glob('*/*/pair.json'):",'''    pairbase=root/'Matched/Pairs'
    pairfiles=pairbase.glob('*/*/pair.json') if days is None else (p for day in days for p in (pairbase/day).glob('*/pair.json'))
    for p in pairfiles:''')
    src=change(src,"    for day_root in sorted(root.iterdir()):","    for day_root in sorted(root.iterdir() if days is None else (root/day for day in days)):")
    src=change(src,"candidates,errors=collect(day);","candidates,errors=collect(day,excluded);")
    src=change(src,"if harmonic.exists() and not","if days is None and harmonic.exists() and not")
    src=change(src,"    for p in dest.glob('*/*/*/record.json'):",'''    previous=dest.glob('*/*/*/record.json') if days is None else (p for day in days for p in dest.glob('*/'+day+'/*/record.json'))
    for p in previous:''')
    return src


def external_patch(src):
    src=change(src,"def ingest(root, *, auto=None, classifier=None):","def ingest(root, *, auto=None, classifier=None, publish=True):")
    src=change(src,"path=_write_training_candidates(root,conn)",'path=_write_training_candidates(root,conn) if publish else home/"reviewed_candidates.csv"')
    return change(src,'    atomic_json(home/"latest.json",report)','    if publish:atomic_json(home/"latest.json",report)')


def pairs_patch(src):
    src=change(src,"    for folder in (root/day).iterdir():\n",'''    for w in (root/source for source,row in sources.items() if row.get("human_grade") in (4,5)):
''')
    a=src.index("        if folder.name.lower()")
    b=src.index("    refs=",a)
    body=src[src.index("            rel=w.relative",a):b]
    src=src[:a]+"\n".join(line[4:] for line in body.splitlines())+"\n"+src[b:]
    src=change(src,"r.get('human_level') in ('confirmed','legacy')","r.get('human_grade') in (4,5)")
    src=change(src,"    refs=[", """    import acoustic_pair_calibration as calibration
    decisions=[row for row in calibration.latest_decisions(root).values() if row.get('day')==day]
    manual={}
    withheld=set()
    for row in decisions:
        bmp,wav=row['bmp'],row['wav']
        withheld.add((bmp,wav))
        if row.get('decision')!='match':continue
        try:
            valid=all(calibration.digest(calibration.safe_source(root,row[k],'.'+k))==row[k+'_sha256'] for k in ('bmp','wav'))
        except (OSError,ValueError,KeyError):
            valid=False
        manual.setdefault(bmp,[]).append(dict(wav=wav,shift=row.get('manual_shift_seconds'),valid=valid))
    refs=[""")
    src=change(src,"    def search(e,shift):","""    existing={e['ar4'] for e in out}
    for bmp in sorted(manual.keys()-existing):
        out.append(dict(ar4=bmp,ar4_utc=0,duration=0,candidates=[],tested=[],issues=[]))
    def search(e,shift):
        if e['ar4'] in manual:
            e['manual_matches']=manual[e['ar4']]
            e['status']='human-confirmed match' if any(m['valid'] for m in e['manual_matches']) else 'saved match needs source verification'
            return""")
    src=change(src,"            if rel in tested","            if (e['ar4'],rel) in withheld:continue\n            if rel in tested")
    src=change(src,"        for i,z in enumerate(e['candidates']):","""        for m in e.get('manual_matches',[]):
            label=h(m['wav'])+' | saved shift '+h(str(m['shift']))+' s'
            if m['valid']:body.append('<p>Human match: <a href="'+h(url(root/m['wav'],dest))+'">'+label+'</a></p>')
            else:body.append('<p>Saved match requires verification: '+label+'</p>')
        for i,z in enumerate(e['candidates']):""")
    src=change(src,"            block+='<li>'","            if r.get('manual_matches'):name=' → '+', '.join(html.escape(m['wav']) for m in r['manual_matches'])\n            block+='<li>'")
    src=change(src,'probable / {len(rs)}','probable / {sum(r["status"]=="human-confirmed match" for r in rs)} human-confirmed / {len(rs)}')
    return change(src,"    for e in out:search(e,0)",'''    from concurrent.futures import ThreadPoolExecutor
    if len(out)>1:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda entry: search(entry,0),out))
    else:
        for e in out:search(e,0)''')


def rt_patch(src):
    src=change(src,"def prepare(root):","def prepare(root,inputs=None):")
    src=change(src,"    care.write_json(root/'Daily_Run_Reports'/'RT_Audio'/'latest.json',report)","    if inputs is None:care.write_json(root/'Daily_Run_Reports'/'RT_Audio'/'latest.json',report)")
    return change(src,"for wav in sorted(folder.glob('*/*.wav')):",'''for wav in sorted(folder.glob('*/*.wav') if inputs is None else inputs):
        if wav.parent.parent.resolve()!=folder.resolve():
            continue''')


def timeline_patch(src):
    src=change(src,"def source_rows(root, day, cfg, info):","def source_rows(root, day, cfg, info, excluded=()):")
    src=change(src,"def refresh(root, cfg=None, days=None):","def refresh(root, cfg=None, days=None, excluded=()):")
    src=change(src,"rows, warnings = source_rows(root, day, cfg, info)","rows, warnings = source_rows(root, day, cfg, info,excluded)")
    src=change(src,"        for path in sorted(folder.iterdir()):","        for path in sorted(folder.iterdir()):\n            if path.with_suffix('.bmp').relative_to(root).as_posix() in excluded:continue")
    return change(src,"    for side in sorted(folder.glob('*.rt.json')):","    for side in sorted(folder.glob('*.rt.json')):\n        if side.with_suffix('').with_suffix('.bmp').relative_to(root).as_posix() in excluded:continue")


def audit_patch(src):
    src=change(src,"def audit(root,days):","def audit(root,days,excluded=()):")
    return change(src,"                try:\n","                if p.with_suffix('').relative_to(root).as_posix() in excluded:continue\n                try:\n")


def progress_patch(src):
    marker=" for bmp,site,media_sha,origin in scans(root):"
    src=change(src,marker,''' cache=None
 if os.environ.get("BAT_DAILY_INDEXED_REPORTS")=="1":
  from daily_reports import ReportCache
  cache=ReportCache(root)
 def inputs():
  if cache is None:
   yield from scans(root)
   return
  for p,_,site,origin in cache.verified_sources():yield p,site.lower(),None,origin
  yield from (managed(root) or ())
  for p in cache.sources(bulk=True):yield p,'historical-unassigned',None,None
  # Preserve noncanonical historical collections. Check their direct membership
  # only when the collection directory has changed since last export.
  for folder in cache.historical_folders():
   for p in folder:yield p,'historical-unassigned',None,None
 for bmp,site,media_sha,origin in inputs():
  rel=bmp.relative_to(root).as_posix()
  sig=cache.parts(bmp) if cache and rel in cache.files else None
  if sig is not None:
   prior=cache.db.execute("SELECT value FROM report_fact WHERE stage='progress' AND path=? AND sig=?",(rel,json.dumps(sig))).fetchone()
   if prior:
    value=json.loads(prior[0])
    if value:rows.append(value)
    continue''')
    marker='   if grade is None:continue'
    src=change(src,marker,'''   if grade is None:
    if sig is not None:cache.db.execute("INSERT OR REPLACE INTO report_fact VALUES ('progress',?,?,?)",(rel,json.dumps(sig),'null'))
    continue''')
    marker="   rows.append(row);by_grade[str(grade)]+=1"
    src=change(src,marker,'''   if sig is not None:
    row['media_sha']=media_sha or cache.fact("digest",bmp,sig[0],lambda:sha(bmp))
    cache.db.execute("INSERT OR REPLACE INTO report_fact VALUES ('progress',?,?,?)",(rel,json.dumps(sig),json.dumps(row)))
'''+marker)
    return change(src," # Content identity,"," if cache:\n  cache.db.commit()\n  cache.db.close()\n # Content identity,")


def model_patch(src):
    src=change(src," ns=ap.parse_args(args);root", " ap.add_argument('--score-only',action='store_true')\n ns=ap.parse_args(args);root")
    src=change(src,"  report(root,ns.open)","  if not ns.score_only:report(root,ns.open)")
    marker=" p=root/'Daily_Run_Reports'/night/'receipt.json'"
    return change(src,marker,marker+"\n candidate=p.with_name('review_first_receipt.json')\n if candidate.is_file() and (not p.exists() or candidate.stat().st_mtime_ns>p.stat().st_mtime_ns):p=candidate")


def pilot_patch(src):
    src=change(src,'    for p in sorted(folder.rglob("*")):','''    if os.environ.get("BAT_DAILY_INDEXED_REPORTS")=="1":
        import sqlite3
        with sqlite3.connect((root/"Daily_Run_Reports"/"Daily_Integration"/"daily_tasks.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
            paths=[root/p for (p,) in db.execute("SELECT path FROM media WHERE kind='local' AND path LIKE ? AND (lower(path) LIKE '%.bmp' OR lower(path) LIKE '%.wav') AND path NOT IN (SELECT path FROM quarantine) AND substr(path,1,length(path)-4)||'.bmp' NOT IN (SELECT path FROM quarantine) ORDER BY path",(night+'/%',))]
    else:
        paths=sorted(folder.rglob("*"))
    for p in paths:''')
    marker='    receipt_file = root / "Daily_Run_Reports" / night / "receipt.json"'
    return change(src,marker,marker+"\n    candidate=receipt_file.with_name('review_first_receipt.json')\n    if candidate.is_file() and (not receipt_file.exists() or candidate.stat().st_mtime_ns>receipt_file.stat().st_mtime_ns):receipt_file=candidate")


def patched(path,fn):
    source=path.read_bytes()
    src=source.decode("utf-8-sig").replace("\r\n","\n")
    new=fn(src)
    compile(new,str(path),"exec")
    if b"\r\n" in source:
        new=new.replace("\n","\r\n")
    return new.encode("utf-8-sig" if source.startswith(b"\xef\xbb\xbf") else "utf-8")


def install(tool,restore=False):
    backup=tool/"Program_Backups"/"review_first_v1"
    manifest=backup/"install.json"
    if manifest.exists():
        saved=json.loads(manifest.read_text())
        for name,expected in saved.items():
            p=tool/name
            if p.exists() and digest(p.read_bytes()) not in (expected["installed"],expected["before"]):
                raise ValueError("Locally modified file: "+str(p))
        if restore:
            for name,expected in saved.items():
                p=tool/name
                if expected["before"] is None:
                    p.unlink(missing_ok=True)
                else:
                    data=(backup/name).read_bytes()
                    if digest(data)!=expected["before"]:
                        raise ValueError("Damaged backup: "+name)
                    write(p,data)
            manifest.unlink()
            return
    elif restore:
        raise ValueError("No review-first installation at "+str(tool))
    for name in ("daily_pipeline.py","review_unreviewed_queue.py","sd_wifi_import.py","rt_audio_daily.py",
                 "external_import.py","post_daily_sync.py","run_integrity.py","bmp_health.py"):
        if not (tool/name).is_file():
            raise FileNotFoundError(tool/name)
    outputs={name:(HERE/name).read_bytes() for name in ("daily_state.py","daily_reports.py","review_first_daily.py")}
    for name,fn in (("model_progress.py",progress_patch),("external_import.py",external_patch),("experimental_review.py",experimental_patch),("post_daily_sync.py",post_patch),("review_dataset.py",inventory_patch),("verified_activity.py",verified_patch),("cumulative_summary.py",summary_patch),("acoustic_pairs.py",pairs_patch),("rt_audio_daily.py",rt_patch),("daily_timeline.py",timeline_patch),("review_plot_audit.py",audit_patch),("Model_Trials_Runtime_v1/model_workflow.py",model_patch),("Model_Trials_Runtime_v1/pilot.py",pilot_patch),("acoustic_pair_calibration.py",acoustic_patch),("fast_review_entrypoint.py",gui_patch)):
        source=(backup if manifest.exists() else tool)/name
        if manifest.exists() and digest(source.read_bytes())!=saved[name]["before"]:
            raise ValueError("Damaged original backup: "+name)
        outputs[name]=patched(source,fn)
    launcher='@echo off\r\nsetlocal\r\ncd /d "%~dp0"\r\n".venv\\Scripts\\python.exe" -u review_first_daily.py %*\r\nset "rc=%errorlevel%"\r\nif not "%BAT_DAILY_NO_PAUSE%"=="1" pause\r\nexit /b %rc%\r\n'
    for name in ("Run Daily with Final Review.bat","Run Daily Scan.bat"):
        if not (tool/name).is_file():
            raise FileNotFoundError(tool/name)
        outputs[name]=launcher.encode()
    if manifest.exists():
        old_manifest=manifest.read_bytes()
        originals={n:(tool/n).read_bytes() for n in outputs}
        try:
            for n,data in outputs.items():
                if originals[n]!=data:write(tool/n,data)
                saved[n]["installed"]=digest(data)
            write(manifest,json.dumps(saved).encode())
        except Exception:
            for n,data in originals.items():write(tool/n,data)
            write(manifest,old_manifest)
            raise
        return
    backup.mkdir(exist_ok=True,parents=True)
    saved={}
    for name,data in outputs.items():
        p=tool/name
        old=p.read_bytes() if p.exists() else None
        if old is not None:
            write(backup/name,old)
        saved[name]={"installed":digest(data),"before":digest(old) if old is not None else None}
    write(manifest,json.dumps(saved).encode())
    try:
        for name,data in outputs.items():
            write(tool/name,data)
    except Exception:
        install(tool,restore=True)
        raise


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--tool",type=Path,default=Path.home()/"Documents"/"Bat"/"BatDailyTool")
    parser.add_argument("--restore",action="store_true")
    args=parser.parse_args()
    install(args.tool.resolve(),args.restore)
    print("Restored previous launchers." if args.restore else "Review-first daily installed.")
