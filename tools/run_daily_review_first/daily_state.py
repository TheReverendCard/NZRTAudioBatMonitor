"""Persistent directory membership and independently committed Bat Daily jobs."""
import json
import os
import re
import sqlite3
import stat
import time
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path

DATE = re.compile(r"\d{8}")
RECORDERS = ("AR4", "Xiao", "XiaoRT", "XiaoSD")


def stamp(path):
    info = path.stat()
    return f"{info.st_size}/{info.st_mtime_ns}"


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 1024)


class State:
    def __init__(self, root):
        self.root = root
        home = root / "Daily_Run_Reports" / "Daily_Integration"
        home.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(home / "daily_tasks.sqlite")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS notes(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS folders(path TEXT PRIMARY KEY, stamp TEXT, children TEXT);
            CREATE TABLE IF NOT EXISTS media(path TEXT PRIMARY KEY, folder TEXT, sig TEXT, kind TEXT);
            CREATE INDEX IF NOT EXISTS by_folder ON media(folder);
            CREATE TABLE IF NOT EXISTS jobs(stage TEXT, item TEXT, PRIMARY KEY(stage,item));
            CREATE TABLE IF NOT EXISTS completed(stage TEXT PRIMARY KEY, generation INTEGER);
            CREATE TABLE IF NOT EXISTS versions(name TEXT PRIMARY KEY, value INTEGER);
            CREATE TABLE IF NOT EXISTS review(path TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS quarantine(path TEXT PRIMARY KEY, sig TEXT, reason TEXT);
            CREATE TABLE IF NOT EXISTS timing(run TEXT, stage TEXT, seconds REAL, result TEXT);
        """)
        self.run = str(time.time_ns())
        self.start=time.perf_counter()
        self.receipts = {}
        self.seal_ns = 0
        legacy = home / "Incremental_State_v3.sqlite3"
        self.archive = None
        try:
            if legacy.is_file():
                # URI interpretation must be enabled on this SQLite connection.
                self.archive = sqlite3.connect(legacy.resolve().as_uri()+"?mode=ro", uri=True, timeout=1)
                self.archive.execute("BEGIN")
                row = self.archive.execute("SELECT value FROM meta WHERE key='seal'").fetchone()
                if row is None:
                    raise ValueError("no completed seal")
                seal = json.loads(row[0])
                if not isinstance(seal, dict) or Path(seal["root"]) != root:
                    raise ValueError("seal belongs to another recording root")
                self.seal_ns = int(datetime.fromisoformat(seal["created_utc"]).timestamp()*1e9)
        except (sqlite3.DatabaseError, OSError, ValueError, TypeError, KeyError, OverflowError) as error:
            self.skip_archive(error)

    def skip_archive(self, error):
        if self.archive is not None:
            self.archive.close()
            self.archive = None
        self.seal_ns = 0
        print(f"Previous incremental checkpoint unavailable ({error}). Continuing with saved daily work and per-day receipts.", flush=True)

    def seed(self, rel, info, zone, recursive):
        """Reuse known membership; do not acknowledge unprocessed additions."""
        if self.archive is None or not self.seal_ns:
            return None
        try:
            if not self.archive.execute("SELECT 1 FROM folder WHERE path=?", (rel,)).fetchone():
                return None
            rows = self.archive.execute("SELECT path,size,mtime_ns FROM source WHERE folder=?", (rel,)).fetchall()
        except sqlite3.DatabaseError as error:
            self.skip_archive(error)
            return None
        for path, size, mtime in rows:
            self.db.execute("INSERT OR IGNORE INTO media VALUES (?,?,?,?)",
                            (path,rel,f"{size}/{mtime}",zone))
        # For nested intake trees rediscover child names once, as the old journal
        # grouped some recorder records and did not persist parent-child lists.
        mark = str(info.st_mtime_ns) if info and info.st_mtime_ns < self.seal_ns and not recursive else "seed"
        self.db.execute("INSERT INTO folders VALUES (?,?,?)", (rel,mark,"[]"))
        self.db.commit()
        return (mark,"[]")

    def put(self, stage, item):
        if stage == "publish":
            self.db.execute("INSERT INTO versions VALUES ('reports',1) ON CONFLICT(name) DO UPDATE SET value=value+1")
        self.db.execute("INSERT OR IGNORE INTO jobs VALUES (?,?)", (stage, item))

    def pending(self, stage):
        return [r[0] for r in self.db.execute("SELECT item FROM jobs WHERE stage=? ORDER BY item DESC", (stage,))]

    def done(self, stage, item):
        self.db.execute("DELETE FROM jobs WHERE stage=? AND item=?", (stage, item))
        self.db.commit()

    @contextmanager
    def activity(self,name):
        start=time.perf_counter()
        try:
            yield
        finally:
            elapsed=time.perf_counter()-start
            changed=self.db.execute("UPDATE timing SET seconds=seconds+? WHERE run=? AND stage=?",(elapsed,self.run,name))
            if not changed.rowcount:
                self.db.execute("INSERT INTO timing VALUES (?,?,?,?)",(self.run,name,elapsed,"elapsed"))

    @contextmanager
    def timed(self, name):
        start = time.perf_counter()
        result = "failed"
        print(name, flush=True)
        try:
            yield
            result = "complete"
        finally:
            elapsed = time.perf_counter() - start
            self.db.execute("INSERT INTO timing VALUES (?,?,?,?)", (self.run, name, elapsed, result))
            self.db.commit()
            print(f"  {elapsed:.2f}s  {result}", flush=True)

    def changed(self, path, zone, removed=False):
        parts = Path(path).parts
        lower = path.lower()
        if zone in ("local","bulk"):
            day = parts[0]
            if zone=="local":
                self.put("night",day)
                if lower.endswith((".bmp",".wav")):
                    self.put("score-night",day)
            if not removed:
                self.put("prepare", path)
            else:
                self.db.execute("DELETE FROM jobs WHERE stage='prepare' AND item=?", (path,))
                if lower.endswith(".bmp"):
                    self.db.execute("DELETE FROM review WHERE path=?", (path,))
                elif lower.endswith(".bmp.data"):
                    self.put("prepare",path[:-5])
        elif zone == "external":
            if not removed:
                self.put("external-file",path)
            self.put("intake", "external")
        elif zone == "receiver":
            group=next((part.casefold() for part in parts if part.casefold() in ("rt","rt_clips","clips")),None)
            task={"rt":"rtlogs","rt_clips":"rtclips","clips":"sd"}.get(group)
            if task and not removed:
                self.put("intake",task)
                self.put(task+"-file",path)
        if zone in ("local","bulk"):
            self.put("summary-file",path)
        self.put("publish", "reports")

    def watch(self, folder, zone, recursive=False, force=False):
        """A directory timestamp controls membership only. Remember child dirs separately."""
        rel = folder.relative_to(self.root).as_posix()
        prior = self.db.execute("SELECT stamp,children FROM folders WHERE path=?", (rel,)).fetchone()
        try:
            info = folder.lstat()
        except FileNotFoundError:
            if not prior:
                return
            info = None
        if info and (linked(info) or not stat.S_ISDIR(info.st_mode)):
            return
        if prior is None:
            prior = self.seed(rel,info,zone,recursive)
        if force and not self.db.execute("SELECT 1 FROM versions WHERE name=?",("first:"+rel,)).fetchone():
            prior = ("current-seed",prior[1]) if prior else None
            self.db.execute("INSERT INTO versions VALUES (?,1)",("first:"+rel,))
        sig = str(info.st_mtime_ns) if info else "absent"
        if prior and prior[0] == sig and not force:
            children = json.loads(prior[1])
        else:
            children, found = [], {}
            if info:
                with os.scandir(folder) as entries:
                    for entry in entries:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if (recursive or (zone=="bulk" and re.fullmatch(r"(?:AR4|Xiao|XiaoRT|XiaoSD)\d{8}",entry.name,re.I))) and not linked(entry.stat(follow_symlinks=False)):
                                children.append(entry.name)
                            continue
                        name = entry.name.lower()
                        extensions = (".bmp",".wav",".bmp.data",".rt.json") if zone == "local" else (".bmp",".wav",".flac",".bmp.data",".json")
                        if zone=="bulk":
                            extensions=(".bmp",".bmp.data")
                        if zone == "receiver" and "rt" in [p.casefold() for p in folder.parts]:
                            extensions += (".log",".txt",)
                        if not name.endswith(extensions):
                            continue
                        detail = entry.stat(follow_symlinks=False)
                        if stat.S_ISREG(detail.st_mode) and not linked(detail):
                            found[rel+"/"+entry.name] = f"{detail.st_size}/{detail.st_mtime_ns}"
            if not prior and zone=="local" and found:
                day=folder.parent.name
                if day not in self.receipts:
                    receipt=self.root/"Daily_Run_Reports"/day/"receipt.json"
                    until,known=0,set()
                    if receipt.is_file():
                        try:
                            data=json.loads(receipt.read_text(encoding="utf-8-sig"))
                            if data.get("status")=="complete":
                                until=int(datetime.fromisoformat(data["finished_utc"]).timestamp()*1e9)
                                known=set(data["inputs"])|set(data["outputs"])
                        except (ValueError,KeyError,TypeError):
                            pass
                    self.receipts[day]=(until,known)
                until,known=self.receipts[day]
                for name,value in found.items():
                    if name in known and int(value.split("/")[1])<=until:
                        self.db.execute("INSERT OR IGNORE INTO media VALUES (?,?,?,?)",(name,rel,value,zone))
                        if force and name.lower().endswith(".bmp"):
                            self.put("prepare",name)
            previous = dict(self.db.execute("SELECT path,sig FROM media WHERE folder=?", (rel,)))
            for path in previous.keys()-found.keys():
                self.changed(path, zone, True)
                self.db.execute("DELETE FROM media WHERE path=?", (path,))
            for path, value in found.items():
                if (zone == "local" and prior and prior[0]=="current-seed" and path.lower().endswith(".bmp")):
                    self.put("prepare",path)
                if previous.get(path) != value:
                    self.changed(path, zone)
                    self.db.execute("INSERT OR REPLACE INTO media VALUES (?,?,?,?)", (path,rel,value,zone))
            self.db.execute("INSERT OR REPLACE INTO folders VALUES (?,?,?)", (rel,sig,json.dumps(children)))
            self.db.commit()
            if prior:
                for missing in set(json.loads(prior[1]))-set(children):
                    self.watch(folder/missing, zone, recursive)
        if recursive:
            for child in children:
                self.watch(folder/child, zone, True, force)

    def dates(self):
        return sorted((p.name for p in self.root.iterdir() if DATE.fullmatch(p.name)
                       and not linked(p.lstat()) and p.is_dir()), reverse=True)

    def discover_day(self, day, force=False):
        self.watch(self.root/day,"bulk",force=force)
        entry=self.db.execute("SELECT children FROM folders WHERE path=?", (day,)).fetchone()
        names=set(json.loads(entry[0]) if entry else [])
        names.update(recorder+day for recorder in RECORDERS)
        for name in sorted(names):
            self.watch(self.root/day/name, "local", force=force)

    def remember_outputs(self,bmp):
        rel=bmp.relative_to(self.root).as_posix()
        if not DATE.fullmatch(rel.split("/")[0]):
            return
        for p in (bmp,Path(str(bmp)+".data")):
            if p.is_file():
                self.db.execute("INSERT OR REPLACE INTO media VALUES (?,?,?,?)",
                                (p.relative_to(self.root).as_posix(),p.parent.relative_to(self.root).as_posix(),stamp(p),"bulk" if DATE.fullmatch(p.parent.name) else "local"))

    def blocked(self, path, sig):
        return bool(self.db.execute("SELECT 1 FROM quarantine WHERE path=? AND sig=?", (path,sig)).fetchone())

    def reject(self, path, sig, reason):
        self.db.execute("INSERT OR REPLACE INTO quarantine VALUES (?,?,?)", (path,sig,str(reason)))
        self.db.execute("DELETE FROM review WHERE path=?", (path,))
        print("Quarantined in place:", path, reason, flush=True)
