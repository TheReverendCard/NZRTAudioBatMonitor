"""Bat Daily post-review stage for the PASS-1 RT field trial."""
import csv
import hashlib
import html
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = 'TheReverendCard/NZRTAudioBatMonitor'
DEVICE = 'bcd3d73f1fb8'
BUILD = 'NZRT-J4-PASS-1'
NZ = ZoneInfo('Pacific/Auckland')
HERE = Path(__file__).resolve().parent

def read(p, default=None):
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.is_file() else default

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        f.write(data.encode('utf8'))
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def fields(line):
    return dict(re.findall(r'(\w+)=([^\s]+)', line))

def observations(folder, db):
    records = defaultdict(set)
    health = set()
    db.execute('CREATE TABLE IF NOT EXISTS cache(path TEXT PRIMARY KEY,size INTEGER,mtime INTEGER,data TEXT)')
    for path in sorted(folder.glob('*.txt')):
        st = path.stat()
        row = db.execute('SELECT data FROM cache WHERE path=? AND size=? AND mtime=?',
                         (str(path), st.st_size, st.st_mtime_ns)).fetchone()
        if row:
            events, diagnostics = json.loads(row[0])
        else:
            events, diagnostics = [], []
            with path.open(encoding='utf8', errors='replace') as f:
                for line in f:
                    if line.startswith('NZRT FIELD health=1 ') or line.startswith('NZRT FIRST_PASS '):
                        diagnostics.append(line.strip())
                    if not line.startswith('NZRT CANDIDATE '):
                        continue
                    v = fields(line)
                    if 'pass_shadow' in v and v.get('clip_request') in ('armed','shared'):
                        events.append([v.get(k,'') for k in ('session','run','seq','clip_owner_seq','bench','first_pass','pass_shadow','pass_shadow_hit','ended_reason')])
            db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?,?)',
                       (str(path), st.st_size, st.st_mtime_ns,json.dumps([events,diagnostics])))
        for sess,run,seq,owner,*details in events:
            records[f'{sess.upper()}:{run}:{owner}'].add((seq,*details))
        health.update(diagnostics)
    db.commit()
    return records, sorted(health)

def collect(root, device, records, profile, backup):
    from review_unreviewed_queue import human_grade
    clips = {}
    by_pcm = {}
    excluded = Counter()
    for p in root.glob('[0-9]'*8+'/XiaoRT*/*.rt.json'):
        info = read(p)
        if info.get('device','').lower() != device:
            continue
        eid = info['rt_event_id'].upper()
        stem = p.name[:-8]
        original = Path(info['wav'])
        meta = read(original.with_suffix('.json'))
        if not meta:
            meta = read(backup/'RT_Clips'/device/stem[:8]/(stem+'.json'),{})
        if meta.get('firmware') != BUILD:
            excluded['older_or_unknown_build'] += 1
            continue
        night = p.parent.parent.name
        # Exclude daytime equipment tests, including normal-route dual-signal WAVs.
        local = datetime.fromtimestamp(info['utc_start'], NZ)
        if 8 <= local.hour < 18 or meta.get('label')=='equipment_test':
            excluded['daytime_or_test'] += 1
            continue
        grade = human_grade(p.with_name(stem+'.bmp.data'))
        rows = records.get(eid,set())
        if any(r[1]=='1' for r in rows):
            excluded['bench'] += 1
            continue
        hits = [int(r[4]) for r in rows if r[1:4]==('0','legacy',profile) and r[4] in ('0','1') and r[5]=='0']
        valid = (meta.get('capture_valid') is True and meta.get('samples')==384000 and
                 meta.get('device_id')==device and meta.get('pcm_sha256')==info['pcm_sha256'] and
                 f"{str(meta.get('session')).upper()}:{meta.get('run')}:{meta.get('seq')}"==eid and
                 meta.get('first_pass')=='legacy' and len(hits)==len(rows) and
                 len({r[0] for r in rows})==len(rows) and any(r[0]==eid.split(':')[2] for r in rows))
        result = max(hits) if hits and valid else None
        item = dict(night=night,grade=grade,hit=result,pcm=info['pcm_sha256'],wav=str(p.with_name(stem+'.wav')))
        if eid in clips and clips[eid]!=item:
            raise ValueError('Conflicting imports for '+eid)
        other=by_pcm.setdefault(item['pcm'],eid)
        if other!=eid:
            raise ValueError('Identical PCM has conflicting recording IDs: '+other+' and '+eid)
        clips[eid]=item
    return clips, dict(excluded)

def health_rates_pass(path,profile):
    totals=defaultdict(Counter)
    with path.open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            counts={k:int(row[k]) for k in ('seconds','dsp_gaps','dsp_drops','clips','incomplete')}
            if min(counts.values())<0 or counts['seconds']==0 or counts['incomplete']>counts['clips']:return False
            totals[row['mode']].update(counts)
    a,b=totals['legacy'],totals[profile]
    return all(a[d]>0 and b[d]>0 and b[n]*a[d]<=a[n]*b[d]
               for n,d in [('dsp_gaps','seconds'),('dsp_drops','seconds'),('incomplete','clips')])

def assess(home, clips, profile, policy):
    frozen=read(HERE/'replay.json')
    stats=Counter()
    nights=defaultdict(Counter)
    weather=read(home/'weather.json',{})
    for v in clips.values():
        grade=v['grade']
        label='bat' if grade in (4,5) else 'noise' if grade in (1,2) else 'possible' if grade==3 else 'ungraded'
        key=label+'_'+{None:'unknown',0:'no_shadow_hit',1:'shadow_hit'}[v['hit']]
        stats[key]+=1
        nights[v['night']][key]+=1
    # Pass identity and receiver coverage are independently reviewed. No time-only joins.
    passes=defaultdict(list)
    seen={}
    pass_nights={}
    ledger=home/'reviewed_passes.csv'
    if ledger.exists():
        with ledger.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                key=row['pass_id'].strip()
                if not key or row['coverage'] not in ('verified','outage','unknown') or not row['reference'].strip():
                    raise ValueError('Incomplete independent-pass ledger row')
                if row['night']<policy['first_night']:
                    continue
                if pass_nights.setdefault(key,row['night'])!=row['night']:
                    raise ValueError('Pass ID reused on different nights')
                eid=row['rt_event_id'].strip().upper()
                if eid and seen.setdefault(eid,key)!=key:
                    raise ValueError('One RT recording assigned to multiple independent passes: '+eid)
                clip=clips.get(eid,{})
                if clip and clip['night']!=row['night']:
                    raise ValueError('Pass and clip nights disagree: '+key)
                result=clip.get('hit') if clip.get('grade') in (4,5) else None
                passes[key].append((row['coverage'],result))
    outcomes=Counter()
    for group in passes.values():
        verified=[hit for coverage,hit in group if coverage=='verified']
        if not verified: outcome='coverage_unknown_or_outage'
        elif 1 in verified: outcome='kept'
        elif None in verified: outcome='unresolved'
        else: outcome='missed'
        outcomes[outcome]+=1
    noise=sum(stats['noise_'+k] for k in ('unknown','no_shadow_hit','shadow_hit'))
    reasons=[]
    unassigned=sum(v['grade'] in (4,5) and k not in seen for k,v in clips.items())
    if unassigned:reasons.append(f'{unassigned} confirmed recordings awaiting independent pass assignment')
    if any(v['grade'] in (4,5) and v.get('replay',{}).get(profile) is False for v in clips.values()):
        reasons.append('Fresh confirmed bat failed saved-WAV replay')
    if not frozen[profile]['known_miss_recovered']:reasons.append('Known regression clip missed')
    if outcomes['kept']<300 or outcomes['missed'] or outcomes['unresolved']:
        reasons.append('Need 300 independent covered passes retained with zero misses or unresolved covered passes')
    if len({v['night'] for v in clips.values() if v['grade'] in (1,2,4,5) and v['hit'] is not None})<2:
        reasons.append('Need verified results from multiple field nights')
    replay_rejects=sum(v['grade'] in (1,2) and v.get('replay',{}).get(profile) is False for v in clips.values())
    if noise and replay_rejects/noise<.8:reasons.append('Fresh saved-WAV noise suppression below 80%')
    if not noise or stats['noise_no_shadow_hit']/noise<.8:
        reasons.append('Field noise suppression below 80% or unavailable')
    health=read(home/'health_review.json',{})
    evidence=home/'health_comparison.csv'
    if not (health.get('device')==DEVICE and health.get('firmware')==BUILD and health.get('profile')==profile
            and health.get('reviewed_noninferior') is True and health.get('reviewer')
            and evidence.is_file() and health.get('sha256')==hashlib.sha256(evidence.read_bytes()).hexdigest()):
        reasons.append('Comparable-load gap, DSP drop and WAV continuity review pending')
    elif not health_rates_pass(evidence,profile):
        reasons.append('Comparative hardware rates worse or unavailable')
    return dict(profile=profile, replay=frozen, field=dict(stats),passes=dict(outcomes),
                nights={k:dict(weather=weather.get(k) if weather.get(k) in ('dry','rainy','mixed') else 'unknown',counts=v) for k,v in sorted(nights.items())},
                reasons=reasons)

def promote(home, backup, report):
    """Use a deterministic intent and distinguish board readback from submission."""
    folder=backup/'RT_Controls'
    folder.mkdir(parents=True,exist_ok=True)
    slot=folder/(DEVICE+'.json')
    ack=read(folder/(DEVICE+'.ack.json'),{})
    profile=report['profile']
    intent=home/('promotion_'+profile+'.json')
    pending=read(intent)
    state=fields(ack.get('first_pass') or '')
    if pending and pending.get('applied_at'):
        return 'applied (board ACK at '+pending['applied_at']+'; historical confirmation)'
    if pending and ack.get('id')==pending['id'] and state.get('active')==profile and state.get('shadow')=='legacy':
        pending['applied_at']=ack.get('accepted_utc','unknown')
        atomic(intent,json.dumps(pending))
        return 'applied (matched board ACK)'
    if pending and read(slot,{}) .get('id')==pending['id']:
        return 'queued; waiting for matching board ACK'
    if pending and pending.get('published'):
        return 'previous request superseded; inspect receiver history'
    if report['reasons']:
        return 'hold'
    # Request status automatically when the latest device ACK has no fresh readback.
    try:
        age=datetime.now(timezone.utc)-datetime.fromisoformat(ack['accepted_utc'])
    except (KeyError,ValueError,TypeError):
        age=timedelta(days=2)
    fresh=(timedelta(0)<=age<=timedelta(days=1) and state.get('version')=='PASS-1')
    if fresh and not (state.get('active')=='legacy' and state.get('shadow')==profile and
                      state.get('requested_active')=='legacy' and state.get('requested_shadow')==profile):
        return 'eligible; board configuration differs from trial (no switch queued)'
    if not fresh:
        intent=home/('status_'+profile+'.json')
        pending=read(intent)
        if pending and read(slot,{}).get('id')==pending['id'] and ack.get('id')!=pending['id']:
            return 'eligible; waiting for board status ACK'
        pending=None
    existing=read(slot,{})
    if existing and existing.get('id')!=ack.get('id'):
        return 'eligible; another receiver command is pending'
    if not pending:
        pending=dict(id=uuid.uuid4().hex,command='pass '+profile+' legacy' if fresh else 'pass status',device=DEVICE)
        atomic(intent,json.dumps(pending))
    # Retire only the acknowledged request. Verify identity again after rename.
    if slot.exists():
        old=folder/(DEVICE+'.retired.'+uuid.uuid4().hex)
        slot.rename(old)
        if read(old)!=existing:
            try:os.link(old,slot)
            except FileExistsError:pass
            raise RuntimeError('Concurrent manual control detected; retained '+str(old))
    staged=folder/(pending['id']+'.trial.tmp')
    atomic(staged,json.dumps({k:pending[k] for k in ('id','command','device')}))
    try:
        os.link(staged,slot)
    except FileExistsError:
        return 'eligible; receiver command slot busy'
    finally:
        staged.unlink(missing_ok=True)
    pending['published']=True
    atomic(intent,json.dumps(pending))
    return 'queued; waiting for matching board ACK' if fresh else 'eligible; queued board status request'

def replay_clip(wav, digest, db):
    import numpy as np
    from features import read_audio,features
    from audible import replay
    version=hashlib.sha256(b''.join((HERE/n).read_bytes() for n in ('audible.py','features.py','winner.json','rt_trial.py'))).hexdigest()
    stat=wav.stat()
    key=f'{version}:{digest}:{stat.st_size}:{stat.st_mtime_ns}'
    row=db.execute('SELECT data FROM replay WHERE key=?',(key,)).fetchone()
    if row:return json.loads(row[0])
    pcm,rate=read_audio(wav)
    if len(pcm)!=384000 or rate!=192000 or hashlib.sha256(pcm.astype('<i2').tobytes()).hexdigest()!=digest:
        raise ValueError('Imported WAV disagrees with receiver receipt')
    model=read(HERE/'winner.json')
    h=np.maximum(features(pcm,rate)@np.asarray(model['weights'],dtype='float32')+np.asarray(model['bias'],dtype='float32'),0)
    evolved=bool(np.any(h[:,0]+h[:,1]-h[:,2]>model['threshold']))
    audible=bool(replay(wav)['audible_check'])
    result=dict(evolved=evolved,audible=audible,either=evolved or audible)
    db.execute('INSERT OR REPLACE INTO replay VALUES (?,?)',(key,json.dumps(result)))
    return result

def summary(r):
    lines=[f"RT PASS-1 daily trial | {r['date']} NZ",f"Candidate: {r['profile']}. Promotion: {r['promotion']}.",
           'Device: '+DEVICE+' | Firmware: '+BUILD,
           'Promotion checks: '+('; '.join(r['reasons']) or 'passed'),
           'Historical replay (confirmed bats kept / 69, graded noise suppressed / 5641):']
    lines.extend(f"- {k}: {v['bat_kept']}, {v['noise_suppressed']}" for k,v in r['replay'].items())
    for title,key in [('Field shadow (reviewed clip associations)','field'),('Independent passes','passes'),
                      ('Fresh saved-WAV replay','fresh_replay'),('Excluded','excluded')]:
        lines.append(title+': '+json.dumps(r[key],sort_keys=True))
    lines.append('Night / weather / field counts:')
    lines.extend(f"- {n} / {v['weather']} / {json.dumps(v['counts'],sort_keys=True)}" for n,v in r['nights'].items())
    lines.append('Coverage unknown and receiver outages are excluded from pass recall. Shared candidates use one recording.')
    return '\n'.join(lines)

def dashboard(home,body,status):
    links='<p><a href="recordings.json">Recording decisions</a> · <a href="diagnostics.txt">Board diagnostics</a> · <a href="https://github.com/'+REPO+'/issues/45">Firmware tracker</a></p>'
    atomic(home/'index.html','<!doctype html><meta charset="utf-8"><title>RT first-pass trial</title><h1>RT first-pass trial</h1>'+links+'<pre style="white-space:pre-wrap">'+html.escape(body+'\n'+status)+'</pre>')
    page=home.parent/'index.html'
    if page.exists():
        source=page.read_text(encoding='utf-8-sig')
        anchor='<h1>Daily processing status</h1>'
        if anchor in source and 'href="RT_First_Pass/index.html"' not in source:
            atomic(page,source.replace(anchor,anchor+'<p><a href="RT_First_Pass/index.html">RT first-pass trial and promotion status</a></p>',1))

def gh(*args, payload=None):
    return subprocess.run(['gh','api',*args],input=json.dumps(payload) if payload is not None else None,
                          text=True,capture_output=True,check=True,timeout=45).stdout

def sync(home):
    out=home/'outbox'
    pending=sorted(out.glob('*.md'))
    if not pending:return
    login=json.loads(gh('user'))['login']
    endpoint=f'repos/{REPO}/issues/45/comments'
    pages=json.loads(gh('--paginate','--slurp',endpoint+'?per_page=100'))
    existing={c['body'].split('\n',1)[0]:c for page in pages for c in page if c['user']['login']==login}
    for p in pending:
        body=p.read_text(encoding='utf8')
        marker=body.split('\n',1)[0]
        old=existing.get(marker)
        if not old or old['body']!=body:
            target=f"repos/{REPO}/issues/comments/{old['id']}" if old else endpoint
            gh('-X','PATCH' if old else 'POST',target,'--input','-',payload={'body':body})
        atomic(home/'published'/p.name,body)
        p.unlink()

def run(root):
    import sys
    sys.path.insert(0,str(HERE))
    sys.path.insert(0,str(root/'BatDailyTool'))
    home=root/'Daily_Run_Reports'/'RT_First_Pass'
    home.mkdir(parents=True,exist_ok=True)
    cfg=read(root/'bat_config.json',{}).get('receiver',{})
    backup=root/Path(cfg.get('backup_root') or 'WiFi_Backup')
    policy=read(home/'policy.json',{'profile':'evolved','first_night':'20261112'})
    profile=policy['profile']
    if profile not in ('evolved','audible'):raise ValueError('Unsupported PASS-1 field profile')
    date=datetime.now(NZ).date().isoformat()
    with sqlite3.connect(home/'cache.sqlite') as db:
        db.execute('CREATE TABLE IF NOT EXISTS replay(key TEXT PRIMARY KEY,data TEXT)')
        events,health=observations(backup/'RT'/DEVICE,db)
        clips,excluded=collect(root,DEVICE,events,profile,backup)
        clips={k:v for k,v in clips.items() if v['night']>=policy['first_night']}
        fresh=Counter()
        for v in clips.values():
            if v['grade'] not in (1,2,4,5):continue
            try:
                d=replay_clip(Path(v['wav']),v['pcm'],db)
            except (ValueError,OSError,EOFError) as exc:
                v['replay_error']=str(exc)
                fresh['unverified']+=1
                continue
            v['replay']=d
            for rule,hit in d.items():
                label='bat' if v['grade']>=4 else 'noise'
                fresh[f"{rule}_{label}_{'kept' if hit else 'suppressed'}"]+=1
        r=assess(home,clips,profile,policy)
        if fresh['unverified']:r['reasons'].append('Unverified graded WAV replay')
    r.update(date=date,excluded=excluded,fresh_replay=dict(fresh),device=DEVICE,firmware=BUILD,policy=policy,
             inputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                     (home/'reviewed_passes.csv',home/'health_review.json',home/'health_comparison.csv',home/'weather.json',HERE/'winner.json',HERE/'replay.json',HERE/'rt_trial.py') if p.is_file()})

    r['promotion']=promote(home,backup,r)
    atomic(home/'diagnostics.txt','\n'.join(health))
    atomic(home/'recordings.json',json.dumps(clips,indent=2))
    body=summary(r)
    atomic(home/'history'/(date+'.json'),json.dumps(r,indent=2))
    atomic(home/'latest.md',body+'\n')
    print(body,flush=True)
    # Preserve distinct revisions when a same-day grade, command or ACK changes.
    serialized=json.dumps(r,sort_keys=True,indent=2)
    revision=hashlib.sha256(serialized.encode()).hexdigest()[:20]
    atomic(home/'revisions'/date/(revision+'.json'),serialized)
    public='<!-- bat-daily-pass1 '+DEVICE+' '+date+' -->\n'+summary(dict(r,nights=dict(list(r['nights'].items())[-14:])))
    if not (home/'published'/(date+'.md')).exists() or (home/'published'/(date+'.md')).read_text(encoding='utf8')!=public:
        atomic(home/'outbox'/(date+'.md'),public)
    else:
        (home/'outbox'/(date+'.md')).unlink(missing_ok=True)
    try:
        sync(home)
    except (OSError,subprocess.SubprocessError,ValueError,KeyError) as exc:
        msg='GitHub pending; Bat Daily will retry. '+str(exc)
    else:msg='GitHub daily reports synchronized to issue #45.'
    atomic(home/'github_status.txt',msg+'\n')
    dashboard(home,body,msg)
    print(msg,flush=True)

if __name__=='__main__':
    import sys
    root=Path(sys.argv[1]).resolve()
    try:
        run(root)
    except Exception as exc:
        import traceback
        home=root/'Daily_Run_Reports'/'RT_First_Pass'
        now=datetime.now(NZ)
        atomic(home/'last_error.txt',traceback.format_exc())
        text=f"RT trial incomplete on {now:%Y-%m-%d}. Review the local last_error.txt and control receipt before interpreting this run."
        atomic(home/'latest.md',text)
        dashboard(home,text,'See last_error.txt')
        atomic(home/'outbox'/(f'{now:%Y-%m-%d}.md'),f'<!-- bat-daily-pass1 {DEVICE} {now:%Y-%m-%d} -->\n'+text)
        try:sync(home)
        except Exception: print('GitHub error report queued for retry.',flush=True)
        raise
