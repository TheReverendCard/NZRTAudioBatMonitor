"""Read-only acoustic retrieval on verified Shed AR4 recordings. All scores are exploratory."""
import hashlib,html,json,os,uuid,wave
from pathlib import Path
from urllib.parse import quote
from functools import lru_cache
from datetime import datetime, timezone
import numpy as np
from PIL import Image
from scipy.signal import correlate,find_peaks,spectrogram
from scipy.ndimage import gaussian_filter1d
from scipy.stats import theilslopes
DT=.002
EDGES=(28000,33500,39000,45000)
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:tmp.write_text(data,encoding='utf8');os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)
def digest(b):return hashlib.sha256(b).hexdigest()
@lru_cache(maxsize=64)
def feature(path,cache,size,mtime):
    # Cache keyed by format revision, full source path, byte length and nanosecond mtime.
    key=digest(repr(('pass-v1',str(path),size,mtime)).encode())
    f=cache/key[:2]/(key+'.npz')
    if f.exists():
        try:
            with np.load(f,allow_pickle=False) as z:return z['bands'],str(z['pcm'])
        except (ValueError,OSError,KeyError):pass
    pcm=''
    if path.suffix.lower()=='.bmp':
        a=np.asarray(Image.open(path).convert('L'),dtype=float)
        if a.shape[1]==64:a=np.rot90(a,-1)
        if a.shape[0]!=64:raise ValueError('AR4 image has no 64-bin axis')
        z=255-a[::-1];hz=(np.arange(64)+.5)*1375;t=np.arange(z.shape[1])*512/176000
    else:
        with wave.open(str(path),'rb') as w:
            rate=w.getframerate();n=w.getnframes()
            if (w.getnchannels(),w.getsampwidth(),w.getcomptype())!=(1,2,'NONE') or rate<90000 or n<256:raise ValueError('unsupported PCM format')
            b=w.readframes(n)
        if len(b)!=2*n:raise ValueError('short WAV')
        pcm=digest(b);hz,t,z=spectrogram(np.frombuffer(b,'<i2').astype(float),rate,nperseg=256,noverlap=192,mode='magnitude')
    dt=t[1]-t[0];grid=np.arange(0,t[-1]+DT/2,DT);bands=[]
    for lo,hi in zip(EDGES,EDGES[1:]):
        part=z[(hz>=lo)&(hz<hi)]
        energy=np.maximum(part-np.median(part,axis=1)[:,None],0).sum(axis=0)
        bands.append(np.interp(grid,t,gaussian_filter1d(energy,.003/dt)))
    bands=np.asarray(bands,dtype='float32');f.parent.mkdir(parents=True,exist_ok=True)
    tmp=f.with_name(key+'.'+uuid.uuid4().hex+'.npz')
    try:np.savez_compressed(tmp,bands=bands,pcm=pcm);os.replace(tmp,f)
    finally:tmp.unlink(missing_ok=True)
    return bands,pcm
def get(p,cache):
    st=p.stat();return feature(p,cache,st.st_size,st.st_mtime_ns)
def peaks(a):
    if len(a)<4 or a.max()<=np.median(a):return np.array([],dtype=int)
    return find_peaks(a,distance=round(.045/DT),prominence=.09*(a.max()-np.median(a)))[0]
def scan(a,b):
    # Lag is the position of SD sample zero on the AR4 axis.
    x=a.sum(axis=0).astype(float);y=b.sum(axis=0).astype(float)
    lags=np.arange(1-len(y),len(x));lo=np.maximum(0,lags);hi=np.minimum(len(x),lags+len(y));n=hi-lo
    def spread(v,l,h):
        c=np.r_[0,np.cumsum(v)];c2=np.r_[0,np.cumsum(v*v)];s=c[h]-c[l];return s,np.maximum(0,c2[h]-c2[l]-s*s/n)
    sx,vx=spread(x,lo,hi);sy,vy=spread(y,lo-lags,hi-lags)
    den=np.sqrt(vx*vy);ok=(n*DT>=min(3,max(1.5,.55*min(len(x),len(y))*DT)))&(den>1e-10)
    r=np.full(len(n),-1.);r[ok]=np.clip((correlate(x,y,method='fft')[ok]-sx[ok]*sy[ok]/n[ok])/den[ok],-1,1)
    # Retain alternate phase alignments instead of treating periodicity as unique.
    ap,bp=peaks(x),peaks(y);hyp=[]
    for _ in range(6):
        i=int(r.argmax());corr=float(r[i]);lag=int(lags[i])
        if corr<=0:break
        r[max(0,i-20):i+21]=-1
        pa=ap[(ap>=lo[i])&(ap<hi[i])];pb=bp+lag;pb=pb[(pb>=lo[i])&(pb<hi[i])]
        pairs=[];j=0
        for k in pa:
            while j<len(pb) and pb[j]<k-10:j+=1
            if j<len(pb) and abs(int(pb[j])-int(k))<=10:pairs.append((int(k),int(pb[j])-lag));j+=1
        hits=len(pairs);agreement=2*hits/max(1,len(pa)+len(pb))
        aa=a[:,lo[i]:hi[i]];bb=b[:,lo[i]-lag:hi[i]-lag]
        ac=aa-aa.mean(axis=1,keepdims=True);bc=bb-bb.mean(axis=1,keepdims=True)
        denom=np.linalg.norm(ac,axis=1)*np.linalg.norm(bc,axis=1)
        band=float(np.mean(np.divide((ac*bc).sum(axis=1),denom,out=np.zeros(3),where=denom>1e-12)))
        rank=.55*corr+.30*agreement+.15*max(0,band)
        hyp.append(dict(score=round(rank,4),r=round(corr,4),pulse_agreement=round(agreement,4),band_r=round(band,4),pulses=hits,lag_s=lag*DT,overlap_s=float(n[i])*DT,span_s=(pairs[-1][0]-pairs[0][0])*DT if hits else 0.,pulse_times_sd_s=[round(j*DT,3) for _,j in pairs]))
    hyp.sort(key=lambda z:-z['score'])
    return hyp
def compare_cached(ar,wav,cache,x,y):
    def ident(p):
        st=p.stat();return [str(p),st.st_size,st.st_mtime_ns]
    key=digest(json.dumps(['rank-v1',ident(ar),ident(wav)]).encode())
    f=cache/'scores'/key[:2]/(key+'.json')
    if f.is_file():
        try:return json.loads(f.read_text())
        except (ValueError,OSError):pass
    result=scan(x,y);write(f,json.dumps(result,allow_nan=False));return result

def assessment(ranked,incomplete=False):
    if not ranked:return 'incomplete search' if incomplete else 'no convincing match'
    z=ranked[0]
    if z['r']<.45 or z['score']<.57 or z['pulses']<4 or z['span_s']<.45:return 'incomplete search' if incomplete else 'no convincing match'
    if incomplete:return 'incomplete search'
    if z['score']-max(z['alternate_lag_score'],ranked[1]['score'] if len(ranked)>1 else 0)<.08:return 'ambiguous'
    return 'probable shared pass'
def clock_groups(records):
    anchors=[];used=set()
    for p in sorted(records,key=lambda z:z['ar4_utc']):
        if p['status']!='probable shared pass':continue
        z=p['candidates'][0]
        if z['wav'] in used or (anchors and p['ar4_utc']-anchors[-1][0]<30):continue
        anchors.append([p['ar4_utc'],z['residual_s']]);used.add(z['wav'])
    groups=[]
    for a in anchors:
        if not groups or abs(a[1]-groups[-1][-1][1])>4:groups.append([])
        groups[-1].append(a)
    out=[]
    for g in groups:
        t,y=np.array(g).T;center=float(np.median(t));slope=0.
        if len(g)>=3 and np.ptp(t)>=1800:slope=float(theilslopes(y,t).slope)
        intercept=float(np.median(y-slope*(t-center)));err=abs(y-(intercept+slope*(t-center)))
        out.append(dict(count=len(g),anchors=g,center_utc=center,from_utc=float(t[0]),to_utc=float(t[-1]),residual_s=intercept,drift_s_per_hour=slope*3600,max_fit_error_s=float(max(err)),usable=len(g)>=2 and max(err)<=2))
    return out

def rt_outcome(z,rows):
    times=z['pulse_times_sd_s'];a=z['sd_utc']+times[0];b=z['sd_utc']+times[-1];rt=[r for r in rows if r['recorder']=='XIAO RT']
    hits=[r for r in rt if r['kind']=='candidate' and r['start']<=b+1 and r['end']>=a-1]
    ids={r['id'] for r in hits};ml=[r for r in rt if 'decision' in r and (r['id'] in ids or a-1<=r['start']+.25<=b+1)]
    nearest=min((r for r in rt if r['kind']=='candidate'),key=lambda r:min(abs(r['start']-a),abs(r['start']-b)),default=None)
    clips=[r for r in rt if r['kind']=='received RT WAV' and r['start']<=a and r['end']>=b]
    coverage='received RT clip spans pulse interval (timestamps rounded)' if clips else 'continuous RT audio coverage unknown'
    return dict(pass_utc=[a,b],covering_rt_clips=[r['source'] for r in clips],rt_triggers=[{'id':r['id'],'class':r.get('shadow_class'),'score':r.get('shadow_score')} for r in hits],ml_results=[{k:r.get(k) for k in ('id','model','mode','decision','probability')} for r in ml],nearest_id=nearest['id'] if nearest else None,nearest_start_minus_pass_start_s=round(nearest['start']-a,2) if nearest else None,coverage=coverage)

def night(root,day,rows,dc):
    cache=root/'Daily_Run_Reports'/'Acoustic_Features_v1'
    window=float(dc.get('acoustic_search_seconds',180))
    if not np.isfinite(window) or not 1<=window<=86400:raise ValueError('acoustic_search_seconds must be 1..86400')
    baseadj=float(dc.get('ar4_clock_adjust_seconds',28));sd=[];errors=[]
    sources={r['source']:r for r in rows if r['recorder']=='XIAO SD'}
    for folder in (root/day).iterdir():
        if folder.name.lower()!='xiao'+day or not folder.is_dir():continue
        for w in sorted(folder.iterdir()):
            if w.suffix.lower()!='.wav':continue
            rel=w.relative_to(root).as_posix();r=sources.get(rel);receipt=None
            try:
                side=Path(str(w)+'.json')
                if side.is_file():
                    meta=json.loads(side.read_text(encoding='utf-8-sig'))
                    if 'start_est_utc_us' in meta:
                        if meta.get('capture_valid') is not True or not meta.get('pcm_sha256'):raise ValueError('unverified receipt')
                        receipt=meta
                if not r and not receipt:raise ValueError('no supported timestamp')
                t=int(receipt['start_est_utc_us'])/1e6 if receipt else float(r['start'])
                if r:duration=r['duration_seconds']
                else:
                    with wave.open(str(w),'rb') as f:duration=f.getnframes()/f.getframerate()
                sd.append((rel,t,duration,receipt,'SD receipt UTC' if receipt else r['clock_note']))
            except Exception as exc:errors.append(rel+': '+str(exc))
    refs=[r for r in rows if r['recorder']=='AR4' and r.get('human_level') in ('confirmed','legacy')]
    out=[]
    for r in refs:
        entry=dict(ar4=r['source'],ar4_utc=r['start'],duration=r['duration_seconds'],candidates=[],tested=[],issues=[]);out.append(entry)
    def search(e,shift):
        tested=set(e['tested']);a=e['ar4_utc']+shift
        for rel,t,dur,receipt,basis in sd:
            if rel in tested or t+dur<a-window or t>a+e['duration']+window:continue
            e['tested'].append(rel)
            try:
                x,_=get(root/e['ar4'],cache);y,pcm=get(root/rel,cache)
                if receipt and pcm!=receipt['pcm_sha256']:raise ValueError('receipt PCM mismatch')
                hs=compare_cached(root/e['ar4'],root/rel,cache,x,y)
                if hs:
                    z=hs[0];residual=t-z['lag_s']-e['ar4_utc']
                    z.update(wav=rel,sd_utc=t,time_basis=basis,residual_s=round(residual,3),total_clock_correction_s=round(baseadj+residual,3),alternate_lag_score=hs[1]['score'] if len(hs)>1 else 0)
                    e['candidates'].append(z)
            except Exception as exc:e['issues'].append(rel+': '+str(exc))
        e['candidates'].sort(key=lambda z:(-z['score'],z['wav']))
        e['status']=assessment(e['candidates'],bool(e['issues'] or errors))
    for e in out:search(e,0)
    models=clock_groups(out)
    for e in out:
        # Expand retrieval only inside bracketed consistent anchors; never use clock agreement to promote an ambiguous pair.
        for m in models:
            if m['usable'] and m['from_utc']<=e['ar4_utc']<=m['to_utc']:
                shift=m['residual_s']+m['drift_s_per_hour']*(e['ar4_utc']-m['center_utc'])/3600
                search(e,shift)
        if e['status']=='probable shared pass':e['rt']=rt_outcome(e['candidates'][0],rows)
        e['candidates']=e['candidates'][:3]
    return dict(day=day,search_seconds=window,wavs=len(sd),issues=errors,anchors_and_clock_segments=clock_groups(out),records=out)

STYLE='<style>body{font:16px system-ui;max-width:1050px;margin:2em auto;color:#193039}article,details{padding:1em;margin:.8em 0;border:1px solid #bdcdd1}svg{width:100%;max-width:850px}a{color:#146978}</style>'
def url(path,start):return quote(os.path.relpath(path,start).replace(os.sep,'/'),safe='/')
def stamp(s):return datetime.fromtimestamp(s,timezone.utc).isoformat(timespec='milliseconds')
def plot(a,b,lag):
    x=a.sum(axis=0);y=b.sum(axis=0);lo=min(0,lag);hi=max(len(x)*DT,lag+len(y)*DT)
    layers=[]
    for v,off,color in ((x,0,'#106386'),(y,lag,'#b6550f')):
        step=max(1,len(v)//1100);idx=np.arange(0,len(v),step)
        # Max pooling retains narrow pulses at display resolution only.
        vv=np.maximum.reduceat(v,idx);pts=' '.join(f'{20+780*(i*DT+off-lo)/(hi-lo):.2f},{90-80*h/max(1e-12,v.max()):.2f}' for i,h in zip(idx,vv))
        layers.append(f'<polyline fill="none" stroke="{color}" points="{pts}"/>')
    return '<svg viewBox="0 0 820 116" role="img" aria-label="Aligned ultrasonic envelopes"><path d="M20 90H800" stroke="#999"/>'+''.join(layers)+f'<text x="20" y="112">{lo:.2f} s</text><text x="400" y="112" text-anchor="middle">seconds from AR4 start</text><text x="800" y="112" text-anchor="end">{hi:.2f} s</text></svg>'
def publish_night(root,report):
    dest=root/'Matched/Acoustic'/report['day'];cache=root/'Daily_Run_Reports/Acoustic_Features_v1';h=html.escape
    body=['<!doctype html><meta charset=utf-8>'+STYLE,'<a href="../index.html">All acoustic reviews</a><h1>Acoustic pairs: '+report['day']+'</h1>',f"<p>{len(report['records'])} reviewed AR4 recordings; {report['wavs']} timestamped SD WAVs; initial search ±{report['search_seconds']:g} s. Blue = AR4, orange = SD. Each trace is scaled independently.</p>",'<a href="pairs.json">Scores, source paths and clock evidence (JSON)</a>']
    for err in report['issues']:body.append('<p>Incomplete inventory: '+h(err)+'</p>')
    for m in report['anchors_and_clock_segments']:
        body.append(f"<p>Clock evidence: {m['count']} independent pass(es); residual {m['residual_s']:+.2f} s beyond configuration; "+(f"bracketed search correction, drift {m['drift_s_per_hour']:+.2f} s/hour, maximum fit residual {m['max_fit_error_s']:.2f} s." if m['usable'] else 'provisional; no correction applied.')+'</p>')
    for e in report['records']:
        body.append(f'<article><h2><a href="{url(root/e["ar4"],dest)}">{h(Path(e["ar4"]).name)}</a>: {e["status"]}</h2><p>{len(e["tested"])} WAVs tested.</p>')
        for err in e['issues']:body.append('<p>'+h(err)+'</p>')
        if 'rt' in e:
            rt=e['rt'];body.append('<p><b>RT during aligned pulses (±1 s):</b> '+h(', '.join(t['id']+' '+str(t['class'] or '') for t in rt['rt_triggers']) or 'no logged trigger')+'; '+h(', '.join(v['id']+' '+v['decision'] for v in rt['ml_results']) or 'no logged neural prediction')+'; '+h(rt['coverage'])+'. '+('Nearest logged trigger '+h(rt['nearest_id'])+f' ({rt["nearest_start_minus_pass_start_s"]:+.1f} s from first matched pulse).' if rt['nearest_id'] and not rt['rt_triggers'] else '')+'</p>')
        for i,z in enumerate(e['candidates']):
            body.append(f'<details {"open" if i==0 else ""}><summary>Rank {i+1}: {h(Path(z["wav"]).name)} | score {z["score"]:.2f}</summary><p><a href="{url(root/z["wav"],dest)}">Open original SD WAV</a> | r={z["r"]:.3f}; {z["pulses"]} aligned pulses; {z["overlap_s"]:.2f} s overlap; SD starts {z["lag_s"]:+.3f} s on AR4 axis; estimated AR4 clock correction {z["total_clock_correction_s"]:+.2f} s.</p>')
            body.append(plot(get(root/e['ar4'],cache)[0],get(root/z['wav'],cache)[0],z['lag_s'])+'</details>')
        body.append('</article>')
    write(dest/'pairs.json',json.dumps(report,indent=2,allow_nan=False));write(dest/'index.html',''.join(body))
def index(root):
    dest=root/'Matched';base=dest/'Acoustic';entries=[]
    for p in sorted(base.glob('*/pairs.json'),reverse=True):
        v=json.loads(p.read_text());rs=v['records'];entries.append(f'<li><a href="{p.parent.name}/index.html">{p.parent.name}</a>: {sum(r["status"]=="probable shared pass" for r in rs)} probable / {len(rs)} reviewed AR4 recordings</li>')
    write(base/'index.html','<!doctype html><meta charset=utf-8>'+STYLE+'<h1>Acoustic paired review</h1><p>Ranked by pulse evidence. Probable matches require review; unpaired recordings are not negatives.</p><ul>'+''.join(entries)+'</ul>')
    p=dest/'index.html';begin='<!-- acoustic ranking begin -->';end='<!-- acoustic ranking end -->'
    latest=next((q for q in sorted(base.glob('*/pairs.json'),reverse=True) if json.loads(q.read_text())['records']),None)
    block=begin+'<section><h2><a href="Acoustic/index.html">Acoustic paired review</a></h2>'
    if latest:
        v=json.loads(latest.read_text())
        block+=f'<p><a href="Acoustic/{v["day"]}/index.html">{v["day"]}: open aligned plots, alternative clips, and RT comparisons</a></p><ul>'
        for r in v['records'][:12]:
            z=r['candidates'];name=' → '+html.escape(Path(z[0]['wav']).name) if z and r['status']=='probable shared pass' else ''
            block+='<li>'+html.escape(Path(r['ar4']).name)+name+': '+r['status']+'</li>'
        block+='</ul>'
    block+='</section>'+end
    if p.exists():
        s=p.read_text(encoding='utf8')
        if begin in s and end in s:
            a=s.index(begin);b=s.index(end,a)+len(end);s=s[:a]+block+s[b:]
        else:
            a=s.find('<article')
            if a>=0:
                b=s.find('<script',a);b=b if b>=0 else len(s)
                s=s[:a]+block+'<details><summary>Legacy timing-window cards (not ranked by acoustic evidence)</summary>'+s[a:b]+'</details>'+s[b:]
            else:s+=block
        write(p,s)
    else:write(p,'<!doctype html><meta charset=utf-8>'+STYLE+block)

def main():
    import argparse,re
    import daily_timeline as d,rt_logs,bat_tool
    from run_integrity import run_lock
    tool=Path(__file__).resolve().parent;root=tool.parent
    ap=argparse.ArgumentParser();ap.add_argument('--night');args=ap.parse_args()
    days=d.report_days(root)
    day=args.night or input('Recording night YYYYMMDD ['+(days[-1] if days else '')+']: ').strip() or (days[-1] if days else '')
    if day not in days:raise SystemExit('No canonical recorder night '+day)
    cfg={**bat_tool.DEFAULTS,**(bat_tool.read_json(tool/'config.json') or {})}
    with run_lock(root,'acoustic pair review'):
        info=d.session_info(root,day);rows,warnings=d.source_rows(root,day,cfg,info)
        lo,hi=info['window'];parsed=rt_logs.load_archives(root)
        for key,kind in [('events','candidate'),('ml','MLP result')]:
            rows.extend(dict(r,recorder='XIAO RT',kind=kind) for r in parsed.get(key,[]) if lo<=r['start']<hi)
        report=night(root,day,rows,{**cfg,**cfg.get('days',{}).get(day,{})});report['source_warnings']=warnings
        publish_night(root,report);index(root)
        print('Open:',root/'Matched/Acoustic'/day/'index.html')
if __name__=='__main__':main()
