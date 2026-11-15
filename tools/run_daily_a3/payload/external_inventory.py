"""Incremental read-only intake inventory. This stage does not classify or publish media."""
import hashlib, os, re, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from annotation_care import _no_links, write_json

SOURCES=(('Mara Kokotoha/Shed','shed-ar4'),('Mara Kokotoha/South','south-ar4'),('Other','other-unresolved'))
def register(root):
    raw=root/'External Data'
    if not raw.is_dir():return
    if not _no_links(raw):raise ValueError('External Data is a link')
    home=root/'Daily_Run_Reports'/'External_Inventory';home.mkdir(parents=True,exist_ok=True)
    errors=[];counts={};t=time.time()
    db=sqlite3.connect(home/'media.sqlite')
    try:
        db.execute('CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY,site TEXT,card_day TEXT,size INTEGER,mtime INTEGER,observed REAL,sha TEXT,last_seen REAL)')
        for part,site in SOURCES:
            source=raw/part
            if not source.exists():continue
            try:
                if any(not _no_links(p) for p in (source,source.parent)):raise ValueError('linked source')
                for d in source.iterdir():
                    if not re.fullmatch(r'[0-9]{8}',d.name) or not d.is_dir() or not _no_links(d):continue
                    for p in d.iterdir():
                        if p.suffix.lower()!='.bmp' or p.name.startswith('.') or not p.is_file() or not _no_links(p):continue
                        rel=p.relative_to(raw).as_posix()
                        try:
                            st=p.stat(); sig=(st.st_size,st.st_mtime_ns)
                            old=db.execute('SELECT size,mtime,observed,sha FROM files WHERE path=?',(rel,)).fetchone()
                            same=old and old[:2]==sig
                            first=old[2] if same else t
                            sha=old[3] if same else None
                            if not sha and same and t-first>=5:
                                with p.open('rb') as f:
                                    h=hashlib.sha256()
                                    for b in iter(lambda:f.read(1<<20),b''):h.update(b)
                                after=p.stat()
                                if sig!=(after.st_size,after.st_mtime_ns):raise ValueError('changed while hashing; deferred')
                                sha=h.hexdigest()
                            db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?)',(rel,site,d.name,*sig,first,sha,t))
                        except (OSError,ValueError) as e:errors.append(rel+': '+str(e))
                    db.commit()
            except (OSError,ValueError) as e:errors.append(part+': '+str(e))
        for site,n,verified,unique in db.execute('SELECT site,count(*),count(sha),count(distinct sha) FROM files WHERE last_seen=? GROUP BY site',(t,)):
            counts[site]=dict(paths=n,verified=verified,distinct_hashes=unique,awaiting_stability=n-verified)
        write_json(home/'latest.json',dict(scanned_utc=datetime.now(timezone.utc).isoformat(),sources=counts,errors=errors,
            scope='Inventory only. Source media/annotations unchanged. No rows imported to Shed reports or review queue. Other source identity remains unresolved.'))
        print('External BMP inventory:',counts,'scan errors:',len(errors),flush=True)
    finally:db.close()
