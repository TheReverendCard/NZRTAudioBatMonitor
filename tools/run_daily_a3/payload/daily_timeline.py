"""Offline three-recorder timeline. Time coincidence is not acoustic identity."""
import csv
import html
import json
import os
import re
import wave
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import rt_logs
import annotation_care

NZ = ZoneInfo('Pacific/Auckland')
CSV_FIELDS = ['id', 'recorder', 'kind', 'start_utc', 'start_nz', 'end_utc',
              'duration_seconds', 'avianz', 'build', 'peak_ratio', 'session',
              'rt_time_coincidences', 'sd_comparison_files', 'source', 'clock_note',
              'human_review', 'human_grade', 'human_review_provenance', 'human_review_time_basis']


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def report_days(root):
    result = []
    if not root.is_dir():
        return result
    for day in sorted(root.iterdir()):
        if not day.is_dir() or not re.fullmatch(r'\d{8}', day.name):
            continue
        found = False
        for sub in day.iterdir():
            if sub.is_dir() and re.fullmatch(r'(?:xiao|ar4|xiaort)\d{8}', sub.name, re.I):
                found |= any(p.is_file() and p.suffix.lower() in ('.wav', '.bmp', '.txt', '.csv')
                             for p in sub.iterdir())
        if found:
            result.append(day.name)
    return result


def session_info(root, day):
    info = {'clips': {}, 'coverage': [], 'gaps': [], 'build': 'unknown', 'warnings': []}
    for folder in sorted((root / day).iterdir()):
        if not folder.is_dir() or not re.fullmatch(r'xiao\d{8}', folder.name, re.I):
            continue
        for path in sorted(folder.glob('session*.txt')):
            current = None
            for line in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
                if line.startswith('XIAO '):
                    info['build'] = line.split(' kind=')[0]
                schedule = re.search(r'SCHEDULE .*?start_utc=(\S+) end_utc=(\S+)', line)
                if schedule:
                    try:
                        info['window'] = tuple(datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
                                               for s in schedule.groups())
                    except ValueError:
                        info['warnings'].append('Unreadable SD schedule: ' + path.name)
                fields = dict(rt_logs.FIELDS.findall(line))
                if line.startswith('FILE '):
                    current = Path(fields.get('path', '')).name
                try:
                    if line.startswith('CLIP ') and current:
                        info['clips'][current] = dict(start=int(fields['start_est_utc_us']) / 1e6,
                            duration=float(fields['duration_seconds']),
                            candidates=int(fields.get('candidates', 0)))
                    if line.startswith('LISTEN_SPAN ') and fields.get('valid') == '1':
                        start = int(fields['first_sample_est_utc_us']) / 1e6
                        info['coverage'].append([start, start + float(fields['sample_seconds'])])
                    if line.startswith('GAP_BEGIN '):
                        info['gaps'].append([int(fields['start_utc_us']) / 1e6, None])
                    if line.startswith('GAP_END ') and info['gaps']:
                        info['gaps'][-1][1] = int(fields['end_utc_us']) / 1e6
                except (ValueError, KeyError):
                    info['warnings'].append('Unreadable session timing line in ' + path.name)
    if 'window' not in info:
        # Night is assigned by NZ collection date, not host clock or UTC date.
        start = datetime.strptime(day, '%Y%m%d').replace(hour=12, tzinfo=NZ)
        info['window'] = (start.timestamp(), (start + timedelta(days=1)).timestamp())
        info['window_basis'] = 'NZ noon-to-noon recording window (SD schedule unavailable)'
    else:
        info['window_basis'] = 'SD session scheduled night (UTC)'
    return info


def avianz_status(path):
    if not path.exists():
        return 'unprocessed'
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise ValueError('Invalid AviaNZ annotation: ' + str(path))
    labels = set()
    for seg in data[1:]:
        if isinstance(seg, list) and len(seg) == 5 and isinstance(seg[4], list):
            for label in seg[4]:
                if label.get('species') in ('Long-tailed bat', 'Short-tailed bat') and float(label.get('certainty', 0)) > 0:
                    labels.add(label['species'])
    if labels:
        return 'AviaNZ candidate: ' + ', '.join(sorted(labels))
    return 'no AviaNZ bat candidate' if data[0].get('Operator') or data[0].get('Reviewer') else 'unprocessed'


def human_review(sidecar, root, ledger):
    """Only explicit, validated *human* review creates a timeline marker.

    AviaNZ's machine-produced Long-tailed/Short-tailed candidates are never
    promoted to human observations. A 1-5 grade applies to a recording, not
    to a precisely localised ultrasonic pulse.
    """
    result = dict(human_level='', human_grade='', human_review='',
                  human_review_provenance='no_annotation', human_review_time_basis='')
    if not sidecar.is_file():
        return result
    state, _who = annotation_care.reviewer_status(sidecar, ledger, root)
    result['human_review_provenance'] = state
    if state not in ('reviewed_metadata', 'reviewed_confirmed'):
        return result
    try:
        data = json.loads(sidecar.read_text(encoding='utf-8-sig'))
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return result
        review = data[0].get('BatDailyReview')
        grade = review.get('grade') if isinstance(review, dict) else None
        if isinstance(grade, bool) or grade not in (1, 2, 3, 4, 5):
            grade = None
        species = set()
        for seg in data[1:]:
            if not isinstance(seg, list) or len(seg) != 5 or not isinstance(seg[4], list):
                continue
            for label in seg[4]:
                if isinstance(label, dict) and label.get('species') in ('Long-tailed bat', 'Short-tailed bat'):
                    if float(label.get('certainty', 0)) > 0:
                        species.add(label['species'])
        if grade is not None:
            result['human_grade'] = grade
        if grade in (4, 5):
            result['human_level'] = 'confirmed'
            who = 'Long-tailed bat' if species == {'Long-tailed bat'} else 'Bat present, species unconfirmed'
            result['human_review'] = f'Human grade {grade}: {who}'
        elif grade == 3:
            result['human_level'] = 'possible'
            result['human_review'] = 'Human grade 3: possible bat (not confirmed)'
        elif grade in (1, 2):
            result['human_review'] = f'Human grade {grade}: likely no bat'
        elif species == {'Long-tailed bat'}:
            # User explicitly confirms legacy reviewed files with sole LT
            # annotation as positive even without a newer confidence grade.
            result['human_level'] = 'legacy'
            result['human_review'] = 'Human-reviewed Long-tailed bat (legacy, ungraded)'
        else:
            result['human_review'] = 'Human-reviewed, no confirmed bat assessment'
        if result['human_level']:
            result['human_review_time_basis'] = 'Recording start, not exact call time'
    except (OSError, ValueError, TypeError):
        # Annotation parse problems must not create a false confirmed marker.
        result['human_review'] = 'Human review unreadable'
    return result



def source_rows(root, day, cfg, info):
    rows, warnings = [], []
    ledger = annotation_care.read_json(root / 'Daily_Run_Reports' / 'Review_Status' / 'ledger.json', {'files': {}})
    dc = {**cfg, **cfg.get('days', {}).get(day, {})}
    offset = float(dc.get('ar4_utc_offset_hours', 12))
    adjust = float(dc.get('ar4_clock_adjust_seconds', 28))
    for folder in sorted((root / day).iterdir()):
        if not folder.is_dir():
            continue
        is_xiao = bool(re.fullmatch(r'xiao\d{8}', folder.name, re.I))
        is_ar4 = bool(re.fullmatch(r'ar4\d{8}', folder.name, re.I))
        if not (is_xiao or is_ar4):
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file():
                continue
            try:
                if is_xiao and path.suffix.lower() == '.wav':
                    match = re.fullmatch(r'(event|periodic)_(\d{8}T\d{6}Z)_\d+', path.stem, re.I)
                    if not match:
                        continue
                    start = datetime.strptime(match[2], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).timestamp()
                    with wave.open(str(path), 'rb') as wav:
                        duration = wav.getnframes() / wav.getframerate()
                    precise = info['clips'].get(path.name)
                    if precise:
                        start = precise['start']
                    annotation = folder / (path.stem + '.bmp.data')
                    recorder, kind, build = 'XIAO SD', match[1].lower(), info['build']
                    clock_note = 'SD session estimated sample UTC' if precise else 'UTC filename; seconds resolution'
                elif is_ar4 and path.suffix.lower() == '.bmp':
                    from PIL import Image
                    start = datetime.strptime(path.stem, '%Y%m%d_%H%M%S').replace(tzinfo=timezone.utc).timestamp()
                    start += -offset * 3600 + adjust
                    with Image.open(path) as im:
                        if 64 not in im.size:
                            raise ValueError('AR4 BMP has no 64-pixel axis')
                        frames = im.height if im.width == 64 else im.width
                        duration = frames * 512 / 176000
                    annotation = Path(str(path) + '.data')
                    recorder, kind, build = 'AR4', 'recorder capture', ''
                    clock_note = f'Provisional configured clock: UTC+{offset:g}, adjustment {adjust:+g}s; not acoustically verified'
                else:
                    continue
                try:
                    label = avianz_status(annotation)
                except (OSError, ValueError, TypeError, AttributeError) as e:
                    label = 'annotation unreadable'
                    warnings.append(path.name + ': ' + str(e))
                review = human_review(annotation, root, ledger)
                rows.append(dict(id=recorder + ':' + path.name, recorder=recorder,
                    kind=kind, start=start, end=start + duration,
                    duration_seconds=duration, avianz=label, build=build,
                    source=path.relative_to(root).as_posix(), clock_note=clock_note, **review))
            except (OSError, ValueError, wave.Error, ZeroDivisionError) as e:
                warnings.append(path.name + ': ' + str(e))
    folder=root/day/('XiaoRT'+day)
    for side in sorted(folder.glob('*.rt.json')):
        try:
            info=json.loads(side.read_text());bmp=folder/(side.name[:-8]+'.bmp')
            if not bmp.is_file() or annotation_care.digest(bmp)!=info['bmp_sha256']:raise ValueError('changed or missing RT BMP')
            t=info['utc_start'];annotation=Path(str(bmp)+'.data')
            rows.append(dict(id='RT audio:'+info['rt_event_id'],recorder='XIAO RT',kind='received RT WAV',start=t,end=t+info['duration'],
                 duration_seconds=info['duration'],avianz=avianz_status(annotation),source=bmp.relative_to(root).as_posix(),
                 clock_note='Receiver receipt UTC; BMP from original RT WAV',**human_review(annotation,root,ledger)))
        except (ValueError,OSError,KeyError,TypeError) as e:warnings.append(side.name+': '+str(e))
    return rows, warnings


def csv_write(path, rows, fields):
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def result_summary(rows):
    machine = [r for r in rows if r.get('avianz', '').startswith('AviaNZ candidate:')]
    states = Counter(r.get('human_review_provenance') or 'unknown'
                     for r in rows if r['recorder'] != 'XIAO RT' or r['kind']=='received RT WAV')
    return dict(avianz_candidate_recordings=len(machine),
                avianz_candidates_by_recorder=dict(Counter(r['recorder'] for r in machine)),
                review_states=dict(states))


def refresh(root, cfg=None, days=None):
    cfg = cfg or {}
    root = root.resolve()
    days = days if days is not None else report_days(root)
    parsed = rt_logs.load_archives(root)
    dest = root / 'Daily_Timeline'
    dest.mkdir(parents=True, exist_ok=True)
    rt_logs.write_json(root / 'XiaoRT_Logs' / 'unresolved.json', parsed['unresolved'])
    rt_logs.write_json(root / 'XiaoRT_Logs' / 'conflicts.json', parsed['conflicts'])
    # Global archive warnings are *not* warnings for each individual night.
    # Preserve their entire wording and severity in one accessible report.
    rt_logs.write_json(dest / 'rt_archive_diagnostics.json', {
        'archive_warnings': parsed['warnings'],
        'archive_warning_count': len(parsed['warnings']),
        'unresolved_rt_count': len(parsed['unresolved']),
        'conflicting_rt_ids': len(parsed['conflicts']),
        'note': 'Terminal-log completeness warnings are archive-wide; they do not prove recorder downtime on any particular night.',
    })
    index_rows = []
    for day in days:
        info = session_info(root, day)
        start, end = info['window']
        rows, warnings = source_rows(root, day, cfg, info)
        rt = [r for r in parsed['events'] if start <= r['start'] < end]
        health = [r for r in parsed['health'] if start <= r['start'] < end]
        # ±1s accounts only for rounded RT UTC. No acoustic agreement is implied.
        for row in rows:
            row['rt_time_coincidences'] = sum(r['start'] <= row['end'] + 1 and r['end'] >= row['start'] - 1 for r in rt)
        for r in rt:
            comparison = [s['source'] for s in rows if s['recorder'] == 'XIAO SD'
                          and r['start'] <= s['end'] + 1 and r['end'] >= s['start'] - 1]
            rows.append(dict(r, recorder='XIAO RT', kind='candidate',
                avianz='not classified by AviaNZ', sd_comparison_sources=comparison,
                sd_comparison_files='; '.join(Path(s).name for s in comparison),
                clock_note='RT declared UTC, rounded to seconds; no RT waveform; SD comparisons are time-only'))
        ml=[m for m in parsed.get('ml',[]) if start<=m['start']<end]
        for m in ml:
            rows.append(dict(m,recorder='XIAO RT',kind='MLP '+m['mode']+' result',avianz='not classified by AviaNZ',duration_seconds=0,clock_note='ML clip start UTC'))
        status=max((v for v in parsed.get('ml_status',[]) if start<=v['start']<end),key=lambda v:v['start'],default={})
        scored=sum(r.get('shadow_class')=='bat_like' for r in rt)
        positives=sum(m['decision']=='bat_candidate' and m['mode']=='shadow' for m in ml)
        for row in rows:
            row['start_utc'] = iso(row['start'])
            row['end_utc'] = iso(row['end'])
            row['start_nz'] = datetime.fromtimestamp(row['start'], NZ).isoformat()
        rows.sort(key=lambda r: (r['start'], r['recorder']))
        notes = info['warnings'] + warnings
        review_states = result_summary(rows)['review_states']
        if review_states and not any(review_states.get(k, 0) for k in ('reviewed_metadata', 'reviewed_confirmed')):
            notes.append('No accepted human reviews were read beside the original recordings. If you reviewed these files, check the .bmp.data location and rebuild after saving. AviaNZ candidate labels remain visible separately.')
        if parsed['conflicts']:
            notes.append(f'{len(parsed["conflicts"])} conflicting RT event IDs; first observation retained. See XiaoRT_Logs/conflicts.json.')
        if not health and not rt:
            notes.append('No timestamped RT records in this night window. This is missing coverage, not a verified zero-detection night.')
        meta = dict(day=day, generated_utc=iso(datetime.now(timezone.utc).timestamp()), **result_summary(rows), window_start_utc=iso(start), window_end_utc=iso(end),
                    window_basis=info['window_basis'], rt_candidates=len(rt),rt_latest_ml_status=status,rt_score_bat_like=scored,rt_valid_ml_results=len(ml),rt_shadow_ml_positives=positives,
                    rt_health_records=len(health), unresolved_rt_total=len(parsed['unresolved']),
                    counts=dict(Counter(r['recorder'] for r in rows)), warnings=notes,
                    rt_archive_warning_count=len(parsed['warnings']),
                    human_review_counts=dict(Counter(r.get('human_level') for r in rows if r.get('human_level'))),
                    sd_listening_seconds=sum(b - a for a, b in info['coverage']),
                    sd_listen_spans=info['coverage'], sd_write_gaps=info['gaps'],
                    rt_collection=rt_logs.read_json(root / 'Daily_Run_Reports' / day / 'XiaoRT' / 'collection.json', {}))
        out = dest / day
        out.mkdir(parents=True, exist_ok=True)
        rt_folder = root / day / ('XiaoRT' + day)
        rt_folder.mkdir(exist_ok=True)
        csv_write(out / 'events.csv', rows, CSV_FIELDS)
        csv_write(rt_folder / 'rt_events.csv', [r for r in rows if r['recorder'] == 'XIAO RT'], CSV_FIELDS)
        csv_write(rt_folder / 'rt_health.csv', [dict(r, utc=iso(r['start'])) for r in health],
                  ['id', 'kind', 'utc', 'session', 'build', 'time_basis', 'source', 'line'])
        rt_logs.write_json(out / 'timeline.json', dict(metadata=meta, events=rows))
        rt_logs.write_json(rt_folder / 'rt_metadata.json', meta)
        # Plain-text per-night view, in addition to immutable full raw captures.
        (rt_folder / 'rt_log.txt').write_text('\n'.join(r['line'] for r in sorted(rt + health, key=lambda r: r['start'])) + '\n', encoding='utf-8')
        import acoustic_pairs
        acoustic_pairs.publish_night(root,acoustic_pairs.night(root,day,rows,{**cfg,**cfg.get('days',{}).get(day,{})}))
        render(out / 'index.html', rows, meta)
        hc = Counter(r.get('human_level') for r in rows if r.get('human_level'))
        index_rows.append(f'<li><a href="{day}/index.html">{day}</a>: {hc.get("confirmed", 0)} graded bat-present recordings, {hc.get("legacy", 0)} legacy verified LT recordings, {hc.get("possible", 0)} possible bat recordings, {len(rt)} RT triggers ({scored} RT-SCORE-1 bat-like); {positives} shadow MLP positives ({len(ml)} valid MLP results); {meta["avianz_candidate_recordings"]} AviaNZ-labelled candidate recordings (not human verification)</li>')
    (dest / 'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Daily timelines</title>'
        '<style>body{font:16px system-ui;max-width:1000px;margin:35px auto;padding:15px}</style>'
        '<h1>Daily recorder timelines</h1><p><a href="../Daily_Run_Reports/index.html">Daily Run status</a></p>'
        '<p>Time coincidence does not confirm a shared call. Missing RT logs are not zero detections. <a href="rt_archive_diagnostics.json">Archive-wide RT log diagnostics</a>.</p><ul>'
        + ''.join(index_rows) + '</ul>', encoding='utf-8')
    import acoustic_pairs
    acoustic_pairs.index(root)
    return {'days': len(days), 'rt_events': len(parsed['events']), 'warnings': parsed['warnings']}


def render(path, rows, meta):
    def link(source):
        return quote(Path(os.path.relpath(path.parents[2] / source, path.parent)).as_posix(), safe='/')
    displays = []
    for r in rows:
        label = r['avianz']
        coincidences = r.get('rt_time_coincidences', '')
        comparison = ' | '.join('<a href="' + link(s) + '">' + html.escape(Path(s).name) + '</a>'
                                for s in r.get('sd_comparison_sources', []))
        if r['recorder'] == 'XIAO RT' and not comparison:
            comparison = 'No saved SD clip at this time'
        if r.get('shadow_class'):label+=' | RT-SCORE-1: '+r['shadow_class']+' '+r['shadow_score']
        if 'decision' in r:label+=' | '+r['model']+': '+r['decision']+' p='+str(r['probability'])
        human = r.get('human_review', '') or 'Not human-confirmed'
        displays.append('<tr data-recorder="' + r['recorder'] + '"><td>' + html.escape(r['start_nz'])
            + '</td><td>' + r['recorder'] + '</td><td>' + html.escape(r['kind']) + '</td><td>'
            + html.escape(human) + '</td><td>' + html.escape(label) + '</td><td>'
            + str(coincidences) + '</td><td>'
            + html.escape(str(r.get('peak_ratio', ''))) + '</td><td>' + comparison
            + '</td><td><a href="' + link(r['source']) + '">'
            + html.escape(Path(r['source']).name) + '</a></td></tr>')
    data = json.dumps([dict(start=r['start'], end=r['end'], recorder=r['recorder'],
                           label=r['id'] + ' | ' + r['start_nz'] + ' | ' + r['avianz'],
                           machine=r.get('avianz', '').startswith('AviaNZ candidate:'),
                           rtmark=('ml' if r.get('decision')=='bat_candidate' and r.get('mode')=='shadow' else 'score' if r.get('shadow_class')=='bat_like' else ''),
                           detail=(str(r.get('model',''))+' '+str(r.get('probability','')) if 'model' in r else 'RT-SCORE-1 '+str(r.get('shadow_score',''))), level=r.get('human_level', ''), grade=r.get('human_grade', ''),
                           human=r.get('human_review', ''), url=link(r['source']))
                       for r in rows], ensure_ascii=True).replace('<', '\\u003c')
    coverage = json.dumps(meta['sd_listen_spans'])
    counts = result_summary(rows)
    count = meta.get('human_review_counts', {})
    human_summary = (f'{count.get("confirmed",0)} reviewed grade 4/5 bat-present recordings; '
                     f'{count.get("legacy",0)} legacy verified Long-tailed recordings; '
                     f'{count.get("possible",0)} grade 3 possible-bat recordings')
    warning_count = len(meta.get('warnings', []))
    diagnostics = ('<details class="diag"><summary>Timing and import notes'
                   + (f' ({warning_count} night-specific notices)' if warning_count else '')
                   + '</summary>'
                   + '<p><a href="../rt_archive_diagnostics.json">Full archived RT diagnostic report</a>. '
                   + 'Unconfirmed completeness is not proof of a listening interruption.</p>'
                   + '<p>RT health points do not establish continuous capture. '
                   + 'AR4 timing uses configured clock correction, not acoustic drift matching.</p>'
                   + ''.join('<p>' + html.escape(s) + '</p>' for s in meta['warnings'])
                   + '</details>')
    page = '''<!doctype html><meta charset="utf-8"><title>Recorder timeline DAY</title>
<style>body{font:15px system-ui;color:#173039;background:#f4f7f8;margin:25px}a{color:#086b80}table{border-collapse:collapse;width:100%;background:white}td,th{padding:9px;text-align:left;border-bottom:1px solid #d7e0e2}svg{background:white;width:100%;min-width:700px}button,select,input{padding:8px;margin:5px}.scroll{overflow-x:auto}.diag{background:#fff;padding:9px 14px;border:1px solid #d7e0e2;border-radius:6px;margin:8px 0 15px}.diag summary{cursor:pointer}.legend{display:flex;gap:18px;flex-wrap:wrap;align-items:center;margin:10px 0;font-size:13px}.legend label{cursor:pointer}.dot{display:inline-block;width:12px;height:12px;border-radius:50%;vertical-align:middle}.verified{background:#087e5c}.legacy{background:#0870a6;border-radius:2px}.possible{background:#b8831b;clip-path:polygon(50% 0,100% 100%,0 100%)}small{color:#485d65}</style>
<h1>Three-recorder timeline: DAY</h1><p><a href="../../Matched/Acoustic/DAY/index.html">Acoustic pair rankings and RT comparison</a></p><p><a href="../index.html">All nights</a> | <a href="../../Daily_Run_Reports/index.html">Daily Run status</a> | <a href="events.csv">Event CSV</a> | <a href="timeline.json">Timing metadata</a></p>
<p>SUMMARY</p><p>RTDETAIL</p><p><strong>AviaNZ-labelled candidates:</strong> MACHINESUMMARY. These are saved annotation labels, not independent human verification.</p><p>Report generated: GENERATED. Review states read: REVIEWSTATES.</p><p><strong>Human-review overlay:</strong> HUMANSUMMARY.</p>
<p>View uses WINDOW. Exact UTC boundaries and imported log cautions are in the metadata.</p>DIAGNOSTICS
<p>Time matches are candidates, not shared-call confirmations. AviaNZ candidate labels are machine outputs; human review markers are shown separately. SD WAVs are separate recordings from the RT microphone input.</p>
<div class="legend"><label><input id="rtshadow" type="checkbox" checked> RT below track: orange ticks = RT-SCORE-1 bat-like; blue circles = shadow MLP bat candidate</label><label><input type="checkbox" id="machine" checked> Hollow purple diamonds: AviaNZ candidates</label><span><i class="dot verified"></i> Human grade 4/5: bat present</span><span><i class="dot legacy"></i> Legacy verified Long-tailed bat</span><label><input type="checkbox" id="possible" checked><i class="dot possible"></i> Show grade 3 possible bats</label></div>
<div class="scroll"><svg id="chart" viewBox="0 0 1100 220" role="img" aria-label="Recorder event timeline with human-review markers"></svg></div>
<small>Markers indicate the <strong>start of a reviewed recording</strong>, not the exact moment of an echolocation call. Click a marker to open its original recording. Event bars are at least 3 pixels wide for visibility and are not call-duration estimates. Pale SD bars show logged listening spans; RT coverage is not inferred from absent events.</small>
<p><select id="rec"><option>All recorders</option><option>AR4</option><option>XIAO SD</option><option>XIAO RT</option></select><input id="search" placeholder="Search file or classification"><span id="count"></span></p>
<div class="scroll"><table><thead><tr><th>NZ start</th><th>Recorder</th><th>Kind</th><th>Human review</th><th>AviaNZ machine output</th><th>RT time coincidences ±1s</th><th>RT peak ratio</th><th>SD comparison audio (time only)</th><th>Original source</th></tr></thead><tbody>ROWS</tbody></table></div>
<script>
const events=DATA,coverage=COVERAGE,svg=document.getElementById('chart');
const ns='http://www.w3.org/2000/svg';function add(tag,attrs,text){let e=document.createElementNS(ns,tag);for(let k in attrs)e.setAttribute(k,attrs[k]);if(text)e.textContent=text;svg.appendChild(e);return e}
const lo=Math.min(WSTART,...events.map(x=>x.start)),hi=Math.max(WEND,...events.map(x=>x.end));const xx=t=>120+950*(t-lo)/Math.max(1,hi-lo),yy={'AR4':45,'XIAO SD':100,'XIAO RT':155},colors={'AR4':'#1d6d91','XIAO SD':'#a85620','XIAO RT':'#5b368f'};
for(let r of Object.keys(yy)){add('text',{x:8,y:yy[r]+6},r);add('line',{x1:120,x2:1070,y1:yy[r],y2:yy[r],stroke:'#d7e0e2'})}
for(let c of coverage)add('rect',{x:xx(c[0]),y:89,width:Math.max(1,xx(c[1])-xx(c[0])),height:22,fill:'#f4dfca'});
for(let e of events){let q=add('rect',{x:xx(e.start),y:yy[e.recorder]-8,width:Math.max(3,xx(e.end)-xx(e.start)),height:16,fill:colors[e.recorder]});let title=document.createElementNS(ns,'title');title.textContent=e.label;q.appendChild(title)}
for(const e of events){if(!e.rtmark)continue;const x=xx(e.start),y=yy[e.recorder]+(e.rtmark==='ml'?28:17);const a=add('a',{href:e.url,'data-rtshadow':'1'});let q=e.rtmark==='ml'?add('circle',{cx:x,cy:y,r:4,fill:'#1678ad'}):add('rect',{x:x-1,y:y-3,width:2,height:6,fill:'#bb5200'});a.appendChild(q);let tt=document.createElementNS(ns,'title');tt.textContent=e.label+' | '+e.detail;a.appendChild(tt);}
document.getElementById('rtshadow').onchange=e=>document.querySelectorAll('[data-rtshadow]').forEach(n=>n.style.display=e.target.checked?'':'none');
// Machine markers below bars; human markers remain above.
for(let e of events){if(!e.machine)continue;let x=xx(e.start),y=yy[e.recorder]+19;
let a=document.createElementNS(ns,'a');a.setAttribute('href',e.url);a.setAttribute('data-machine','1');a.setAttribute('aria-label',e.label);svg.appendChild(a);
let q=document.createElementNS(ns,'polygon');q.setAttribute('points',`${x},${y-5} ${x+5},${y} ${x},${y+5} ${x-5},${y}`);q.setAttribute('fill','white');q.setAttribute('stroke','#7a3699');q.setAttribute('stroke-width','1.5');a.appendChild(q);
let title=document.createElementNS(ns,'title');title.textContent=e.label;a.appendChild(title);}
document.getElementById('machine').addEventListener('change',e=>{for(let a of document.querySelectorAll('[data-machine]'))a.style.display=e.target.checked?'':'none'});
// Add human-review markers only after bars, so they remain visible.
for(let e of events){if(!e.level)continue;let y=yy[e.recorder]-19,x=xx(e.start);let a=document.createElementNS(ns,'a');a.setAttribute('href',e.url);a.setAttribute('aria-label',e.human+'; recording start '+e.label);if(e.level==='possible')a.setAttribute('data-possible','1');svg.appendChild(a);
 let stem=document.createElementNS(ns,'line');for(let [k,v] of Object.entries({x1:x,y1:y+5,x2:x,y2:y+10,stroke:'#33454c','stroke-width':1.5}))stem.setAttribute(k,v);a.appendChild(stem);
 let shape=document.createElementNS(ns,e.level==='possible'?'polygon':e.level==='legacy'?'rect':'circle');let attrs=e.level==='possible'?{points:(x)+','+(y-6)+' '+(x-6)+','+(y+5)+' '+(x+6)+','+(y+5),fill:'#b8831b'}:e.level==='legacy'?{x:x-4.5,y:y-4.5,width:9,height:9,fill:'#0870a6'}:{cx:x,cy:y,r:e.grade===5?6:5,fill:'#087e5c'};attrs.stroke='#fff';attrs['stroke-width']=1.4;for(let [k,v] of Object.entries(attrs))shape.setAttribute(k,v);a.appendChild(shape);
 let title=document.createElementNS(ns,'title');title.textContent=e.human+' | '+e.label+' | Recording start, NOT exact call time';a.appendChild(title)}
document.getElementById('possible').addEventListener('change',e=>{for(let a of document.querySelectorAll('[data-possible]'))a.style.display=e.target.checked?'':'none'});
for(let i=0;i<=8;i++){let t=lo+(hi-lo)*i/8;add('text',{x:xx(t),y:203,'text-anchor':'middle','font-size':12},new Date(t*1000).toLocaleTimeString('en-NZ',{timeZone:'Pacific/Auckland',hour:'2-digit',minute:'2-digit',hour12:false}))}
function filter(){let n=0;document.querySelectorAll('tbody tr').forEach(r=>{let ok=(rec.value==='All recorders'||r.dataset.recorder===rec.value)&&r.textContent.toLowerCase().includes(search.value.toLowerCase());r.hidden=!ok;if(ok)n++});document.getElementById('count').textContent=n+' rows'}const rec=document.getElementById('rec'),search=document.getElementById('search');rec.onchange=filter;search.oninput=filter;filter();
</script>'''
    replacements = {'DAY': meta['day'], 'SUMMARY': html.escape(', '.join(f'{k}: {v}' for k, v in meta['counts'].items())
                    + f'; RT health records: {meta["rt_health_records"]}'),
                    'MACHINESUMMARY': html.escape(str(counts['avianz_candidate_recordings']) + ' (' + ', '.join(f'{k}: {v}' for k,v in counts['avianz_candidates_by_recorder'].items()) + ')'),
                    'GENERATED': html.escape(meta.get('generated_utc', 'not recorded in this saved report')),
                    'REVIEWSTATES': html.escape(', '.join(f'{k}: {v}' for k,v in counts['review_states'].items())),
                    'RTDETAIL': f'RT-SCORE-1 bat-like: {meta.get("rt_score_bat_like",0)}; valid MLP results: {meta.get("rt_valid_ml_results",0)}; shadow MLP positives: {meta.get("rt_shadow_ml_positives",0)}. No result means no prediction.' + html.escape((' Last status: '+', '.join(f'{k}={v}' for k,v in meta['rt_latest_ml_status'].items() if k in ('wav','completed','skipped_busy','gaps','wav_ack','wav_failed'))) if meta.get('rt_latest_ml_status') else ''),
                    'WINDOW': html.escape(meta['window_basis']),
                    'HUMANSUMMARY': html.escape(human_summary), 'DIAGNOSTICS': diagnostics,
                    'ROWS': ''.join(displays), 'DATA': data, 'COVERAGE': coverage,
                    'WSTART': str(datetime.fromisoformat(meta['window_start_utc']).timestamp()),
                    'WEND': str(datetime.fromisoformat(meta['window_end_utc']).timestamp())}
    # Substitute each placeholder once in the template, never inside user data.
    pattern = re.compile(r'\b(' + '|'.join(replacements) + r')\b')
    path.write_text(pattern.sub(lambda m: replacements[m[0]], page), encoding='utf-8')
