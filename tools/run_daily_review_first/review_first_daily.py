"""Review-first entry point for the installed Windows BatDailyTool."""
import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
import shutil
from zoneinfo import ZoneInfo
import subprocess
import sys
import tempfile
import time
import wave
from unittest.mock import patch

from daily_state import State, stamp

TOOL = Path(__file__).resolve().parent


def command(name, *args):
    subprocess.run([sys.executable, "-u", str(TOOL/name), *map(str,args)], cwd=TOOL, check=True)


def path_for(root, rel):
    path = root / rel
    if not path.resolve().is_relative_to(root) or path.resolve() != path:
        raise ValueError("Invalid or linked recorder path: "+rel)
    return path


def bmp_for(path):
    if path.name.lower().endswith(".bmp.data"):
        return path.with_suffix("")
    if path.name.lower().endswith(".rt.json"):
        return path.with_suffix("").with_suffix(".bmp")
    return path.with_suffix(".bmp")


def group_signature(bmp):
    paths = (bmp,Path(str(bmp)+".data"),bmp.with_suffix(".wav"))
    return "|".join(stamp(p) if p.exists() else "-" for p in paths)


def prepare(state, daily, auto, days):
    from bmp_health import inspect_bmp
    from review_unreviewed_queue import human_grade
    from PIL import Image
    batches = defaultdict(dict)
    checked = set()
    for rel in state.pending("prepare"):
        day = rel.split("/")[0]
        if day not in days:
            continue
        path = path_for(state.root, rel)
        if not path.is_file():
            state.done("prepare", rel)
            continue
        bmp = bmp_for(path)
        key = bmp.relative_to(state.root).as_posix()
        if state.blocked(key, group_signature(bmp)):
            state.done("prepare", rel)
            continue
        wav = path.suffix.lower() == ".wav"
        if wav and path.parent.name.startswith("XiaoRT") and not bmp.with_suffix(".rt.json").is_file():
            # Receiver intake owns provenance and will publish this receipt.
            state.done("prepare", rel)
            continue
        if wav:
            try:
                with wave.open(str(path)) as source:
                    count = source.getnframes()
                    if count < 1:
                        raise ValueError("Empty WAV")
                    source.setpos(count-1)
                    if len(source.readframes(1)) != source.getsampwidth()*source.getnchannels():
                        raise ValueError("Truncated WAV")
            except (EOFError, OSError, ValueError, wave.Error) as exc:
                state.reject(key,group_signature(bmp),exc)
                state.done("prepare",rel)
                continue
            if not path.parent.name.startswith("XiaoRT"):
                try:
                    with state.activity("WAV to BMP conversion"):
                        daily.core.export_wav({"path":path},path.parent)
                except (ValueError,EOFError,wave.Error) as exc:
                    state.reject(key,group_signature(bmp),exc)
                    state.done("prepare",rel)
                    continue
            elif not bmp.is_file():
                raise RuntimeError("RT receipt exists but converted BMP is missing: "+str(bmp))
            if path.parent.name == "Xiao"+day:
                state.put("flac",rel)
            # Persist the successful WAV export independently of the CLI batch.
            state.put("prepare",key)
            state.done("prepare",rel)
        if state.blocked(key,group_signature(bmp)):
            state.done("prepare",rel)
            continue
        if not bmp.exists() or (bmp.parent.name.startswith("XiaoRT") and not bmp.with_suffix(".rt.json").is_file()):
            state.done("prepare",rel)
            continue
        if bmp in checked:
            if bmp in batches[day]:
                batches[day][bmp].append(rel)
            else:
                state.done("prepare",rel)
            continue
        checked.add(bmp)
        reason = inspect_bmp(bmp)
        if not reason:
            try:
                with Image.open(bmp) as source:
                    source.load()
            except (ValueError,OSError,EOFError) as exc:
                reason = str(exc)
        side = Path(str(bmp)+".data")
        if not reason and side.exists() and not daily.processed(bmp) and not daily.safe_conversion_placeholder(bmp):
            reason = "Unreadable or invalid existing annotation"
        if reason:
            state.reject(key,group_signature(bmp),reason)
            state.done("prepare",rel)
            continue
        if human_grade(side) is not None:
            state.db.execute("DELETE FROM review WHERE path=?", (key,))
            state.done("prepare",rel)
            continue
        batches[day].setdefault(bmp,[]).extend((rel,key))
    for day, files in batches.items():
        items = list(files)
        for start in range(0,len(items),100):
            subset = items[start:start+100]
            work = state.root/"Daily_Run_Reports"/day
            work.mkdir(parents=True,exist_ok=True)
            if any(not daily.processed(bmp) for bmp in subset):
                scratch=Path(tempfile.mkdtemp(prefix="control_",dir=work))
                with state.timed("AviaNZ baseline "+day):
                    daily.classify(subset,state.root,scratch,"ReviewFirst",auto)
                # These are isolated input copies; immutable machine snapshots are canonical.
                shutil.rmtree(scratch)
            for bmp in subset:
                if not daily.processed(bmp):
                    raise RuntimeError("Baseline classification incomplete: "+str(bmp))
                state.remember_outputs(bmp)
                state.db.execute("INSERT OR IGNORE INTO review VALUES (?)",(bmp.relative_to(state.root).as_posix(),))
                for rel in files[bmp]:
                    state.done("prepare",rel)


def run_queue(state, daily, auto, excluded=()):
    from review_unreviewed_queue import ReviewQueue
    from fast_review_entrypoint import start
    import shutil
    root = state.root
    queue = ReviewQueue(root)
    queue.home.mkdir(parents=True,exist_ok=True)
    previous = queue.load()["items"]
    def sync():
        old = dict(queue.load()["items"])
        outcome = queue.sync()
        for k in old.keys()-queue.load()["items"].keys():
            rel = old[k]["source"]
            state.remember_outputs(root/rel)
            state.put("publish","reports")
            state.put("summary-file",rel)
            if rel.startswith("Daily_Run_Reports/External_Import/Managed/"):
                state.put("final","external training")
            day = rel.split("/")[0]
            if len(day)==8 and day.isdigit():
                state.put("night",day)
            state.db.execute("DELETE FROM review WHERE path=?", (rel,))
        state.db.commit()
        return outcome
    sync()
    candidates = {r[0] for r in state.db.execute("SELECT path FROM review")} - set(excluded)
    candidates.update(v["source"] for v in previous.values() if v["source"] not in excluded)
    candidates = sorted(candidates,reverse=True)
    def sources():
        for rel in candidates:
            bmp = path_for(root,rel)
            if bmp.is_file() and not state.blocked(rel,group_signature(bmp)):
                yield bmp,rel
    queue.sources = sources
    pending,totals = queue.scan()
    for error in getattr(queue,"scan_errors",[]):
        if isinstance(error,str):
            rel,_,reason=error.partition(": ")
            if rel in candidates and reason:
                state.reject(rel,group_signature(root/rel),reason)
    allowed = {rel for _,rel in pending}
    for rel in set(candidates)-allowed:
        state.db.execute("DELETE FROM review WHERE path=?", (rel,))
    state.db.commit()
    if not pending:
        return set()
    # Recover a missing comparison baseline only for the actual review batch.
    # Never copy a historical human sidecar into Backup.
    repairs = [bmp for bmp,_ in pending[:queue.limit] if not (bmp.parent/"Backup"/(bmp.name+".data")).exists()]
    if repairs:
        with tempfile.TemporaryDirectory(prefix="baseline_",dir=queue.home.parent) as tmp:
            copies = []
            for i,bmp in enumerate(repairs):
                dest = Path(tmp)/str(i)/bmp.name
                dest.parent.mkdir()
                shutil.copy2(bmp,dest)
                copies.append(dest)
            daily.classify(copies,root,Path(tmp),"Control",auto)
            for bmp,copy in zip(repairs,copies):
                daily.care.machine_snapshot(bmp,engine=auto.get("recogniser","NZ Bats"),origin="reconstructed_control",source_data=Path(str(copy)+".data"))
    with patch.object(queue,"scan",lambda:(pending,totals)):
        prepared = queue.prepare()
    if prepared["errors"]:
        raise RuntimeError(str(prepared["errors"]))
    items = queue.load()["items"]
    if not items:
        return set()
    batch = {v["source"] for v in items.values()}
    if not batch-set(excluded):
        return set()
    first = min(items,key=lambda k:(items[k]["source"] not in queue.priority,k))
    try:
        if not state.db.execute("SELECT 1 FROM timing WHERE run=? AND stage='Time to first review launch'",(state.run,)).fetchone():
            elapsed=time.perf_counter()-state.start
            print(f"Launching FastAviaNZ after {elapsed:.2f}s; {len(batch)} recordings staged.",flush=True)
            state.db.execute("INSERT INTO timing VALUES (?,?,?,?)",(state.run,"Time to first review launch",elapsed,"ready"))
            state.db.commit()
        with patch.dict(os.environ, BAT_REVIEW_FIRST="1"):
            rc = start(root/"AviaNZ_CLI_Source_Test",queue.active/first)
        if rc:
            raise RuntimeError(f"FastAviaNZ exited with code {rc}")
    finally:
        sync()
    return batch


def intake(state,daily,auto,day):
    root = state.root
    for kind in state.pending("intake"):
        with state.timed("Import "+kind):
            if kind=="external":
                import external_import as ext
                from bmp_health import inspect_bmp
                changed=state.pending("external-file")
                rawroot=root/"External Data"
                rows=[]
                sources={}
                for file in changed:
                    bmp=bmp_for(path_for(root,file))
                    rel=bmp.relative_to(rawroot).as_posix()
                    if rel in sources or not bmp.is_file():
                        continue
                    site=next((site for prefix,site in ext.SITES if rel.startswith(prefix+"/")),None)
                    if site is None or not bmp.parent.name.isdigit():
                        continue
                    key=bmp.relative_to(root).as_posix()
                    sig=group_signature(bmp)
                    if state.blocked(key,sig):
                        continue
                    problem=inspect_bmp(bmp)
                    if problem:
                        if not state.blocked(key,sig):
                            state.reject(key,sig,problem)
                        continue
                    st=bmp.stat()
                    age=time.time()-st.st_mtime
                    if 0<=age<5:
                        time.sleep(5-age)
                    if stamp(bmp)!=f"{st.st_size}/{st.st_mtime_ns}":
                        raise RuntimeError("External file is still copying: "+str(bmp))
                    rows.append((rel,site,bmp.parent.name,st.st_size,st.st_mtime_ns,ext.sha(bmp)))
                    sources[rel]=key
                if rows:
                    with patch.object(ext,"_candidate_rows",lambda root:rows):
                        result=ext.ingest(root,auto=auto,classifier=daily.classify,publish=False)
                    state.db.execute("INSERT OR REPLACE INTO notes VALUES (?,?)",("external",json.dumps(result)))
                    unresolved=[]
                    for issue in result.get("issues",[]):
                        name,sep,why=issue.partition(": ")
                        if sep and name in sources and "still copying" not in why and "changed since inventory hash" not in why:
                            key=sources[name]
                            state.reject(key,group_signature(root/key),why)
                        else:
                            unresolved.append(issue)
                    if unresolved:
                        raise RuntimeError(str(unresolved))
                    with sqlite3.connect(root/ext.REL/"imports.sqlite") as conn:
                        for rel in sources:
                            row=conn.execute("SELECT managed_rel FROM media WHERE source_rel=?", (rel,)).fetchone()
                            if row and row[0]:
                                state.db.execute("INSERT OR IGNORE INTO review VALUES (?)",row)
                    state.put("final","external training")
                for file in changed:
                    state.done("external-file",file)
            else:
                import_receiver(state,kind)
            state.done("intake",kind)


def import_receiver(state,kind):
    import sd_wifi_import as sd
    import rt_audio_daily
    import rt_logs
    root=state.root
    task=kind+"-file"
    files=state.pending(task)
    pairs=defaultdict(list)
    for rel in files:
        path=path_for(root,rel)
        if kind=="rtlogs":
            if path.suffix.lower()==".txt" and path.is_file():
                pairs[path].append(rel)
            else:
                state.done(task,rel)
        else:
            wav=path.with_suffix("") if path.name.lower().endswith(".wav.json") else path.with_suffix(".wav")
            if wav.is_file():
                pairs[wav].append(rel)
            else:
                state.done(task,rel)
    rt_stats=dict(found=len(pairs),new_bmps=0,verified=0,issues=[])
    for path,rels in pairs.items():
        key=path.relative_to(root).as_posix()
        sig=receiver_signature(path)
        if not state.blocked(key,sig):
            if kind=="rtlogs":
                timestamp=rt_logs.backup_timestamp(path)
                if timestamp:
                    day=timestamp.astimezone(ZoneInfo("Pacific/Auckland")).strftime("%Y%m%d")
                    with patch.object(rt_logs,"find_recent_wifi_logs",lambda *_:[path]):
                        result=rt_logs.import_recent_wifi_backup(root,day)
                    if result.get("errors"):
                        state.reject(key,sig," | ".join(result["errors"]))
                    if result.get("status")=="wifi_imported":
                        for offset in (-1,0,1):
                            target=(timestamp+timedelta(days=offset)).strftime("%Y%m%d")
                            if (root/target).is_dir():
                                state.put("night",target)
            elif kind=="sd":
                if sd.DEVICE.fullmatch(path.parent.parent.name) and sd.SESSION.fullmatch(path.parent.name) and sd.WAV_NAME.fullmatch(path.name):
                    try:
                        sd.verify_wav(path)
                    except (ValueError,EOFError,wave.Error,OSError) as exc:
                        state.reject(key,sig,exc)
                    else:
                        target=sd.destination_dir(root,sd.night_for(path.name))/path.name
                        for src,dst in [(path,target)]+[(v,target.with_name(v.name)) for v in sd.sidecars(path)]:
                            outcome,_=sd.safe_copy(src,dst,False)
                            if outcome=="conflict":
                                state.reject(key,sig,"Conflicting canonical file: "+str(dst))
                                break
            else:
                products,issues=rt_audio_daily.prepare(root, inputs=[path])
                rt_stats["verified"]+=sum(map(len,products.values()))
                rt_stats["issues"].extend(issues)
                if issues:
                    state.reject(key,sig," | ".join(issues))
        for rel in rels:
            state.done(task,rel)
    if kind=="rtclips" and pairs:
        rt_stats.pop("new_bmps")
        rt_stats["scope"]="Changed receiver WAVs in this intake"
        state.db.execute("INSERT OR REPLACE INTO notes VALUES (?,?)",("rtclips",json.dumps(rt_stats)))
        state.put("final","RT audio status")
        state.db.commit()


def receiver_signature(path):
    return "|".join(stamp(p) if p.is_file() else "-" for p in
                    (path,path.with_suffix(".json"),path.with_name(path.name+".json")))


def report(state,daily,days):
    import acoustic_pairs
    import flac_archive
    from daily_timeline import refresh
    from cumulative_summary import update_summary
    from review_unreviewed_queue import human_grade
    import post_daily_sync as post
    root=state.root
    cfg={**daily.core.DEFAULTS,**daily.core.read_json(TOOL/"config.json",{})}
    grouped=defaultdict(list)
    for rel in state.pending("flac"):
        if (root/rel).is_file():
            grouped[rel.split("/")[0]].append(rel)
        else:
            state.done("flac",rel)
    for day,rels in grouped.items():
        with state.timed("FLAC "+day):
            with patch.object(flac_archive,"rebuild_index",lambda root: None):
                flac_archive.export_day(root,day,[root/r for r in rels])
            state.put("final","flac index")
            for rel in rels:
                state.done("flac",rel)
    if "flac index" in state.pending("final"):
        flac_archive.rebuild_index(root)
        state.done("final","flac index")
    if "RT audio status" in state.pending("final"):
        row=state.db.execute("SELECT value FROM notes WHERE key='rtclips'").fetchone()
        daily.core.write_json(root/"Daily_Run_Reports"/"RT_Audio"/"latest.json",json.loads(row[0]))
        state.done("final","RT audio status")
    if "external training" in state.pending("final"):
        from external_import import refresh_training_candidates
        refresh_training_candidates(root)
        row=state.db.execute("SELECT value FROM notes WHERE key='external'").fetchone()
        if row:
            from external_import import atomic_json,REL
            atomic_json(root/REL/"latest.json",json.loads(row[0]))
        state.done("final","external training")
    for day in state.pending("night"):
        if day not in days:
            state.done("night",day)
            continue
        with state.timed("Recorder summaries "+day):
            # The installed timeline publishes the authoritative acoustic report once.
            for recorder,folder in (("AR4","AR4_Summaries"),("Xiao","Experimental_Summaries")):
                bmps=[p for p in (root/day/(recorder+day)).glob("*.bmp") if not state.blocked(p.relative_to(root).as_posix(),group_signature(p))]
                daily.export_summaries(bmps,root/"Daily_Run_Reports"/day/folder)
            state.put("final","timelines")
            state.put("timeline-day",day)
            state.done("night",day)
    if "timelines" in state.pending("final"):
        dirty=state.pending("timeline-day")
        if dirty:
            with state.timed("Recorder timelines"):
                import experimental_review
                from review_plot_audit import audit
                import re
                index=root/"Daily_Timeline"/"index.html"
                pattern=r'<li><a href="(\d{8})/index.html".*?</li>'
                previous=index.read_text(encoding="utf-8") if index.exists() else ""
                rows={m[1]:m[0] for m in re.finditer(pattern,previous)}
                quarantined={r[0] for r in state.db.execute("SELECT path FROM quarantine")}
                # Match the installed timeline while excluding the same invalid media as review.
                import rt_logs
                from daily_reports import archived_rt
                with patch.object(rt_logs,"load_archives",archived_rt):
                    refresh(root,cfg,dirty,excluded=quarantined)
                current=index.read_text(encoding="utf-8")
                rows.update({m[1]:m[0] for m in re.finditer(pattern,current)})
                merged=re.sub(r"<ul>.*?</ul>",lambda _: "<ul>"+"".join(rows[d] for d in sorted(rows) if d in days)+"</ul>",current,count=1,flags=re.S)
                temp=index.with_suffix(".tmp")
                temp.write_text(merged,encoding="utf-8")
                temp.replace(index)
                if audit(root,dirty,excluded=quarantined):
                    raise RuntimeError("Grade-to-timeline reconciliation failed")
                if experimental_review.sync(root,daily.core,days=dirty,excluded=quarantined):
                    raise RuntimeError("Experimental review reconciliation needs attention")
                for complete in dirty:
                    receipt=root/"Daily_Run_Reports"/complete/"review_first_receipt.json"
                    daily.core.write_json(receipt,{"status":"complete","day":complete,"finished_utc":daily.now(),"scope":"Review-first intake, baseline, reconciliation and timeline"})
                for day in dirty:
                    state.done("timeline-day",day)
        state.done("final","timelines")
    if state.pending("publish"):
        with state.timed("Cumulative summary"):
            changed=state.pending("summary-file")
            update_summary(root,cfg,changed=changed if (root/"AviaNZ_Summary"/"ledger.json").is_file() else None,
                           excluded={r[0] for r in state.db.execute("SELECT path FROM quarantine")})
            for rel in changed:
                state.done("summary-file",rel)
        checks=[]
        for day in days:
            folder=root/"Daily_Run_Reports"/day
            r=daily.core.read_json(folder/"review_first_receipt.json",{}) or daily.core.read_json(folder/"receipt.json",{})
            if r:
                checks.append((day,r.get("status")=="complete",r.get("scope",r.get("status","unknown"))))
        quarantine_count=state.db.execute("SELECT count(*) FROM quarantine").fetchone()[0]
        daily.status_page(root,checks,[f"{quarantine_count} quarantined input(s). See Daily Timing and Quarantine for details."] if quarantine_count else [])
        generation=state.db.execute("SELECT value FROM versions WHERE name='reports'").fetchone()[0]
        def measured(name,cmd,**kwargs):
            if state.db.execute("SELECT 1 FROM completed WHERE stage=? AND generation=?", (name,generation)).fetchone():
                return {"status":"complete","reused":True}

            with state.timed(name):
                if name=="model_trials":
                    for day in state.pending("score-night"):
                        if day in days:
                            with state.timed("Model inference "+day):
                                scored=post.stage_command("model_"+day,[*cmd,"--night",day,"--score-only"],**kwargs)
                            if scored.get("status")!="complete":
                                return scored
                        state.done("score-night",day)
                    cmd=[*cmd[:2],"refresh",*cmd[3:]]
                outcome=post.stage_command(name,cmd,**kwargs)
                if outcome.get("status")=="complete":
                    state.db.execute("INSERT OR REPLACE INTO completed VALUES (?,?)",(name,generation))
                return outcome
        with state.timed("Final reports and model comparisons"), patch.dict(os.environ,BAT_DAILY_INDEXED_REPORTS="1"):
            if post.run(root,scan_rc=0,review_rc=0,call=measured):
                raise RuntimeError("Post-daily reporting incomplete")
        state.done("publish","reports")


@contextmanager
def exclusive(path):
    # OS lock is released automatically if Python is interrupted.
    with path.open("a+b") as f:
        if not path.stat().st_size:
            f.write(b"0")
            f.flush()
        f.seek(0)
        if os.name=="nt":
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--force","--full-rescan",action="store_true",help="Refresh expected input memberships")
    p.add_argument("--day",help="Inspect the named recording date for in-place edits")
    p.add_argument("--status",action="store_true",help="Show last timing breakdown and quarantined inputs")
    args=p.parse_args()
    if args.status:
        db=TOOL.parent/"Daily_Run_Reports"/"Daily_Integration"/"daily_tasks.sqlite"
        if not db.exists():
            print("No review-first run recorded yet.")
            return 0
        with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True) as conn:
            for (run,) in conn.execute("SELECT DISTINCT run FROM timing ORDER BY run DESC LIMIT 5"):
                print(datetime.fromtimestamp(int(run)/1e9, ZoneInfo("Pacific/Auckland")).strftime("%Y-%m-%d %H:%M %Z"))
                for stage,elapsed,status in conn.execute("SELECT stage,seconds,result FROM timing WHERE run=? ORDER BY seconds DESC",(run,)):
                    print(f"{elapsed:9.2f}s  {status:9} {stage}")
            print("Quarantine (original files retained)")
            for path,reason in conn.execute("SELECT path,reason FROM quarantine ORDER BY path"):
                print(path,reason)
        return 0
    import daily_pipeline as daily
    from run_integrity import run_lock
    root=TOOL.parent.resolve()
    state=State(root)
    home=root/"Daily_Run_Reports"/"Daily_Integration"
    with exclusive(home/"review_first.lock"):
        with run_lock(root,"review-first"):
            auto=daily.ensure_source_cli(root,daily.core.read_json(daily.AUTO,{}))
            days=state.dates()
            now=datetime.now(ZoneInfo("Pacific/Auckland"))
            today=now.strftime("%Y%m%d")
            yesterday=(now-timedelta(days=1)).strftime("%Y%m%d")
            recent={today,yesterday}
            if args.day:
                datetime.strptime(args.day,"%Y%m%d")
                recent.add(args.day)
            if days:
                recent.add(max((d for d in days if d<=today),default=today))
            for key,sig in list(state.db.execute("SELECT path,sig FROM quarantine")):
                receiver=key.startswith("WiFi_Backup/")
                if (receiver_signature(root/key) if receiver else group_signature(root/key))!=sig:
                    state.db.execute("DELETE FROM quarantine WHERE path=?",(key,))
                    if receiver:
                        state.changed(key,"receiver")
                    elif key.startswith("External Data/"):
                        state.put("external-file",key)
                        state.put("intake","external")
                    else:
                        bmp=root/key
                        state.put("prepare",bmp.with_suffix(".wav").relative_to(root).as_posix() if bmp.with_suffix(".wav").exists() else key)
                        state.put("night",key.split("/")[0])
                    state.put("publish","reports")
            state.db.commit()
            # A single edited manual calibration ledger can affect several nights.
            import acoustic_pair_calibration as calibration
            anchor=calibration.ledger_file(root)
            key="anchor-ledger"
            token=stamp(anchor) if anchor.exists() else "missing"
            state.db.execute("CREATE TABLE IF NOT EXISTS controls(name TEXT PRIMARY KEY,value TEXT)")
            previous=state.db.execute("SELECT value FROM controls WHERE name=?", (key,)).fetchone()
            if previous and previous[0]!=token:
                for row in calibration.ledger(root)["history"]:
                    if row.get("day") in days:
                        state.put("night",row["day"])
                state.put("publish","reports")
            state.db.execute("INSERT OR REPLACE INTO controls VALUES (?,?)",(key,token))
            state.db.commit()
            with state.timed("Current recorder intake and baseline"):
                for day in recent:
                    first=not state.db.execute("SELECT 1 FROM versions WHERE name=?",("active:"+day,)).fetchone()
                    state.discover_day(day,args.force or day==args.day or first)
                    state.db.execute("INSERT OR IGNORE INTO versions VALUES (?,1)",("active:"+day,))
                state.db.commit()
                prepare(state,daily,auto,recent)
            shown=set()
            first_index=not state.db.execute("SELECT 1 FROM versions WHERE name='initialized'").fetchone()
            if first_index:
                with state.timed("Current FastAviaNZ review before first historical index"):
                    shown=run_queue(state,daily,auto)
            with state.timed("Historical additions and external intake folders"):
                from external_import import SITES
                for part,_ in SITES:
                    state.watch(root/"External Data"/part,"external",True,args.force)
                for part in ("Clips","RT","RT_Clips"):
                    state.watch(root/"WiFi_Backup"/part,"receiver",True,args.force)
                intake(state,daily,auto,max((d for d in days if d<=today),default=today))
                days=state.dates()
                for day in days:
                    state.discover_day(day,args.force)
                prepare(state,daily,auto,set(days))
            state.db.execute("INSERT OR REPLACE INTO versions VALUES ('initialized',1)")
            state.db.commit()
            with state.timed("FastAviaNZ review of prepared recordings"):
                while True:
                    batch=run_queue(state,daily,auto,shown)
                    if not batch:
                        break
                    shown.update(batch)
                    # Closing mid-batch keeps ungraded files pending for next time.
                    from review_unreviewed_queue import ReviewQueue
                    if ReviewQueue(root).load()["items"]:
                        break
            daily.create_next_day_folders(root,today)
        report(state,daily,days)
        state.db.execute("INSERT INTO timing VALUES (?,?,?,?)",(state.run,"Total elapsed (includes human review)",time.perf_counter()-state.start,"complete"))
        state.db.commit()
        if os.name=="nt" and (root/"Daily_Run_Reports"/"index.html").exists():
            os.startfile(root/"Daily_Run_Reports"/"index.html")
        print("Timing and quarantine database:",home/"daily_tasks.sqlite")
    return 0


if __name__=="__main__":
    sys.exit(main())
