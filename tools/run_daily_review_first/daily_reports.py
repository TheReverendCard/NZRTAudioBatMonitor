"""Derived recording facts for incremental whole-project reports."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path


class ReportCache:
    def __init__(self,root):
        self.root=root
        self.db=sqlite3.connect(root/"Daily_Run_Reports"/"Daily_Integration"/"daily_tasks.sqlite")
        self.db.execute("CREATE TABLE IF NOT EXISTS report_fact(stage TEXT,path TEXT,sig TEXT,value TEXT,PRIMARY KEY(stage,path))")
        self.files=dict(self.db.execute("SELECT path,sig FROM media WHERE kind IN ('local','bulk')"))
        self.excluded={r[0] for r in self.db.execute("SELECT path FROM quarantine")}
        self._manifests={}

    def sources(self,bulk=False):
        for name in sorted(self.files):
            if name in self.excluded or not name.lower().endswith(".bmp"):
                continue
            parts=Path(name).parts
            if len(parts)==(2 if bulk else 3):
                yield self.root/name

    def parts(self,bmp):
        rel=bmp.relative_to(self.root).as_posix()
        return [self.files.get(rel),self.files.get(rel+".data"),self.files.get(rel[:-4]+".wav"),
                self.files.get(rel[:-4]+".rt.json")]

    def fact(self,stage,bmp,sig,build):
        rel=bmp.relative_to(self.root).as_posix()
        signature=json.dumps(sig,sort_keys=True)
        old=self.db.execute("SELECT value FROM report_fact WHERE stage=? AND path=? AND sig=?",(stage,rel,signature)).fetchone()
        if old:
            return json.loads(old[0])
        value=build()
        self.db.execute("INSERT OR REPLACE INTO report_fact VALUES (?,?,?,?)",(stage,rel,signature,json.dumps(value)))
        return value

    def inventory_rows(self,module,root,ledger):
        out=[];errors=[];canon={}
        bulk_stats=dict(folders=0,bmps_seen=0,added=0,no_annotations=0,unknown_recording_timestamp=0,duplicates_skipped=0)
        bulk_dirs=set()
        for bulk in (False,True):
            for bmp in self.sources(bulk):
                args={}
                rel=bmp.relative_to(root).as_posix()
                folder=bmp.parent
                if not bulk and not re.fullmatch(r"(AR4|Xiao)\d{8}",folder.name,re.I):
                    continue
                try:
                    if bulk:
                        bulk_dirs.add(folder)
                        bulk_stats["bmps_seen"]+=1
                        day=module.legacy_bulk_night(bmp.name)
                        if day is None:
                            bulk_stats["unknown_recording_timestamp"]+=1
                            errors.append(dict(file=str(bmp),error="Unknown recording timestamp"))
                            continue
                        if rel+".data" not in self.files:
                            bulk_stats["no_annotations"]+=1
                            continue
                        def content(p):
                            return self.fact("digest",p,self.parts(p)[0],lambda:module.care.digest(p))
                        peers=canon.get(bmp.name,[])
                        if peers and any(content(bmp)==content(other) for other in peers):
                            bulk_stats["duplicates_skipped"]+=1
                            continue
                        if peers:
                            errors.append(dict(file=str(bmp),error="Same filename with different BMP bytes"))
                        args=dict(night=day,recorder="AR4Bulk"+folder.name,collection=folder.relative_to(root).as_posix(),date_source="filename_noon_to_noon")
                    if folder not in self._manifests:
                        self._manifests[folder]=module.care.read_json(folder/"Backup"/"manifest.json",{}).get("files",{})
                    sig=self.parts(bmp)+[ledger.get("files",{}).get(rel+".data"),self._manifests[folder].get(bmp.name+".data")]
                    row=self.fact("inventory2",bmp,sig,lambda:module.inspect_file(root,folder,bmp,ledger,**args))
                    if row is not None:
                        out.append(row)
                        canon.setdefault(bmp.name,[]).append(bmp)
                        if bulk:
                            bulk_stats["added"]+=1
                except (ValueError,TypeError,OSError,KeyError) as exc:
                    errors.append({"file":str(bmp),"error":str(exc)})
        bulk_stats["folders"]=len(bulk_dirs)
        self.db.commit()
        return out,errors,bulk_stats

    def historical_folders(self):
        from daily_state import linked
        ignored={"backup","work","avianz_experimental","matched","daily_run_reports","training_flac","fastreviewqueue","original_annotation_history"}
        dates=[self.root/r[0] for r in self.db.execute("SELECT path FROM folders WHERE length(path)=8")]
        def members(path,is_day):
            sig=str(path.stat().st_mtime_ns)
            def read():
                if is_day:
                    return [p.name for p in path.iterdir() if p.is_dir() and not linked(p.lstat()) and p.name.lower() not in ignored and not (re.fullmatch(r"(?:ar4|xiao|xiaort)\d{8}",p.name,re.I) and p.name.endswith(path.name))]
                return [p.name for p in path.glob("*.bmp") if p.is_file() and not linked(p.lstat())]
            return self.fact("legacy-folders" if is_day else "legacy-members",path,sig,read)
        for day in dates:
            if not day.is_dir():continue
            for name in members(day,True):
                sub=day/name
                if sub.is_dir() and not linked(sub.lstat()):
                    yield [sub/n for n in members(sub,False)]

    def verified_sources(self):
        for bmp in self.sources():
            m=re.fullmatch(r"(ar4|xiao|xiaort)(\d{8})",bmp.parent.name,re.I)
            if not m or m[2]!=bmp.parent.parent.name:
                continue
            recorder={"ar4":"AR4","xiao":"XiaoSD","xiaort":"XiaoRT"}[m[1].lower()]
            if recorder=="XiaoRT" and self.parts(bmp)[3] is None:
                continue
            yield bmp,recorder,"Shed",None


def archived_rt(root):
    """Reuse validated raw-log text and parsed results, including cross-file clock anchors."""
    from daily_state import stamp
    import rt_logs
    home=root/"Daily_Run_Reports"/"Daily_Integration"
    db=sqlite3.connect(home/"daily_tasks.sqlite")
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS rt_text(path TEXT PRIMARY KEY,sig TEXT,text TEXT,warning TEXT);
            CREATE TABLE IF NOT EXISTS rt_result(id INTEGER PRIMARY KEY,result TEXT);
        """)
        folder=root/"XiaoRT_Logs"/"Raw"
        # Membership is checked on the one live raw-log directory only.
        # Both names in the immutable receiver bundle participate in its cache key.
        prior=dict(db.execute("SELECT path,sig FROM rt_text"))
        changed=False
        for path in sorted(folder.glob("*.txt")):
            rel=path.relative_to(root).as_posix()
            side=path.with_suffix(".json")
            sig=stamp(path)+"|"+(stamp(side) if side.exists() else "-")
            if prior.pop(rel,None)==sig:
                continue
            text=None
            warning=None
            try:
                meta=rt_logs.read_json(side,{})
                data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=meta.get("sha256"):
                    warning="Archived RT log hash mismatch; excluded: "+path.name
                elif not meta.get("complete") and meta.get("method")!="saved_log_import":
                    warning="Incomplete USB download excluded: "+path.name
                else:
                    text=data.decode("utf-8-sig",errors="replace")
                    if not meta.get("complete"):
                        warning="Imported terminal log has unknown completeness: "+path.name
            except (OSError,ValueError) as exc:
                warning=path.name+": "+str(exc)
            db.execute("INSERT OR REPLACE INTO rt_text VALUES (?,?,?,?)",(rel,sig,text,warning))
            changed=True
        for key in prior:
            db.execute("DELETE FROM rt_text WHERE path=?",(key,))
            changed=True
        cached=db.execute("SELECT result FROM rt_result WHERE id=1").fetchone()
        if cached and not changed:
            return json.loads(cached[0])
        rows=list(db.execute("SELECT path,text,warning FROM rt_text ORDER BY path"))
        parsed=rt_logs.parse_logs([(p,t) for p,t,_ in rows if t is not None])
        parsed["warnings"]=[w for _,_,w in rows if w]
        db.execute("INSERT OR REPLACE INTO rt_result VALUES (1,?)",(json.dumps(parsed),))
        db.commit()
        return parsed
    finally:
        db.close()
