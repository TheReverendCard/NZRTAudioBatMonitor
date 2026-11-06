"""Retrieve the existing MeshCore flash journal and import timestamped NZRT logs.

Only `nzrt status` and `log` are sent. Never erase logs or set device time.
Raw exports are immutable; repeated exports are deduplicated by session/run/seq.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
EOF = re.compile(rb"(?m)^\s*(?:->\s*)?EOF\s*\r?$")
FIELDS = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def read_json(path, default=None):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def valid_epoch(value):
    try:
        result = float(value)
        return result if 1577836800 <= result < 4102444800 else None
    except (ValueError, TypeError):
        return None


def parse_logs(texts):
    """Two passes: collect session clock anchors, then deduplicate event records.

    texts is [(source_path, text), ...]. UTC on candidate lines is authoritative.
    Health uptime is converted only with a same-session anchor. Unsynced
    candidates remain unresolved, never assigned to the download day.
    """
    records = []
    builds, anchors = {}, {}
    for source, text in texts:
        current = None
        for line in text.splitlines():
            match = re.search(r'\bNZRT\s+([A-Z_]+)\b', line)
            if not match:
                continue
            kind = match[1]
            fields = dict(FIELDS.findall(line[match.start():]))
            if kind == 'SESSION':
                current = fields.get('id')
                if current:
                    builds[current] = fields.get('build', 'unknown')
            session = fields.get('session', current)
            fields['_session'] = session
            records.append((source, line[match.start():].strip(), kind, fields))
            if not session:
                continue
            epoch = valid_epoch(fields.get('utc'))
            uptime = fields.get('uptime_ms')
            if uptime is None and fields.get('uptime', '').endswith('s'):
                try:
                    uptime = float(fields['uptime'][:-1]) * 1000
                except ValueError:
                    pass
            if epoch and uptime is not None and fields.get('time_source') != 'UNSYNCED':
                try:
                    anchors.setdefault(session, []).append((float(uptime) / 1000, epoch))
                except ValueError:
                    pass
    events, health, unresolved, conflicts = {}, {}, {}, []
    for source, line, kind, f in records:
        session = f['_session'] or 'unknown'
        if kind == 'CANDIDATE':
            key = ':'.join([session, f.get('run', '?'), f.get('seq', '?')])
            if session == 'unknown' or f.get('seq') is None:
                key = hashlib.sha256(line.encode()).hexdigest()[:24]
            scored = (builds.get(session) == 'NZRT-FIELD-PILOT-5' or bool(f.get('score_version')))
            if scored:
                try:
                    valid_score = (f.get('unverified') == '1' and bool(f.get('score_version'))
                                   and f.get('class') in ('bat_like', 'uncertain')
                                   and 0 <= int(f.get('score', '-1')) <= 100
                                   and int(f.get('pulses', '-1')) >= 0
                                   and f.get('ended_reason') in ('0','1','2','3'))
                except ValueError:
                    valid_score = False
                if not valid_score:
                    unresolved.setdefault(key, {'source': source, 'line': line,
                        'reason': 'Incomplete or invalid scored RT record; raw bytes retained'})
                    continue
            stamp = valid_epoch(f.get('utc_start'))
            if not stamp or f.get('time_source') in ('UNSYNCED', 'UNKNOWN'):
                unresolved.setdefault(key, {'source': source, 'line': line,
                                             'reason': 'No trustworthy candidate UTC'})
                continue
            end = valid_epoch(f.get('utc_end')) or stamp
            try:
                duration = max(0, float(f['to_ms']) - float(f['from_ms'])) / 1000
            except (KeyError, ValueError):
                duration = max(0, end - stamp)
            row = dict(id=key, session=session, run=f.get('run', ''),
                       sequence=f.get('seq', ''), start=stamp,
                       end=max(end, stamp + duration), duration_seconds=duration,
                       peak_ratio=f.get('peak', '').rstrip('x'),
                       time_source=f.get('time_source', 'declared UTC'),
                       timestamp_resolution_seconds=1,
                       build=builds.get(session, 'unknown'), source=source, line=line,
                       classification='unverified ultrasonic activity')
            # Scores are heuristic firmware outputs, always kept separate
            # from AviaNZ and human review labels. Old builds remain unscored.
            for field in ('score_version', 'score', 'shadow', 'pulses', 'short_pulses',
                          'pulse_mean_ms', 'pulse_max_ms', 'gap_mean_ms',
                          'freq_mean_khz', 'freq_min_khz', 'freq_max_khz',
                          'narrow_fraction', 'duty', 'harmonic_fraction', 'ended_reason'):
                row[field] = f.get(field, '')
            row['rt_class'] = f.get('class', '')
            if row['rt_class'] in ('bat_like', 'uncertain') and row['score_version']:
                row['classification'] = 'RT heuristic: ' + row['rt_class'] + ' (unverified)'
            unresolved.pop(key, None)
            old = events.get(key)
            if old:
                # Import provenance does not make a new event. Conflicting
                # payloads are reported and the first observation is retained.
                if any(old[k] != row[k] for k in ('start', 'end', 'peak_ratio', 'score_version', 'score', 'rt_class')):
                    conflicts.append({'id': key, 'first_source': old['source'],
                                      'other_source': source, 'other_line': line})
            else:
                events[key] = row
        elif kind in ('FIELD', 'BAND', 'DAY_MODE', 'TIME_SYNC', 'SESSION', 'SCORE', 'SCORE_POLICY'):
            stamp = valid_epoch(f.get('utc'))
            clock = 'declared UTC'
            if stamp is None and session in anchors:
                try:
                    up = float(f.get('uptime', '').rstrip('s'))
                    a, b = min(anchors[session], key=lambda x: abs(x[0] - up))
                    stamp = b + up - a
                    clock = 'estimated from same-session uptime anchor'
                except ValueError:
                    pass
            if stamp is not None:
                token = hashlib.sha256(line.encode()).hexdigest()[:24]
                health.setdefault(token, dict(id=token, kind=kind, session=session,
                    start=stamp, time_basis=clock, source=source, line=line,
                    build=builds.get(session, 'unknown')))
    return {'events': sorted(events.values(), key=lambda r: (r['start'], r['id'])),
            'health': sorted(health.values(), key=lambda r: r['start']),
            'unresolved': list(unresolved.values()), 'conflicts': conflicts}


def archive_log(root, data, method, complete, **extra):
    directory = root / 'XiaoRT_Logs' / 'Raw'
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    # A duplicate download does not replace the original capture or receipt.
    for old in directory.glob('*.json'):
        meta = read_json(old, {})
        existing = old.with_suffix('.txt')
        if (meta.get('sha256') == digest and existing.exists()
                and hashlib.sha256(existing.read_bytes()).hexdigest() == digest
                and meta.get('complete') == bool(complete)
                and (complete or meta.get('method') == method)):
            return existing, meta
    stem = datetime.now(timezone.utc).strftime('capture_%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:8]
    path = directory / (stem + '.txt')
    with path.open('xb') as f:
        f.write(data)
    meta = dict(captured_utc=utc_now(), method=method, complete=bool(complete),
                sha256=digest, bytes=len(data), **extra)
    write_json(path.with_suffix('.json'), meta)
    return path, meta


def import_log(root, path):
    data = Path(path).read_bytes()
    # A saved terminal export might have no EOF. Its records are still useful,
    # but its completeness is explicitly unknown in the report.
    marker = EOF.search(data.rstrip())
    finished = bool(marker and marker.end() == len(data.rstrip()))
    return archive_log(root, data, 'saved_log_import', finished,
                       original_filename=Path(path).name)


def read_journal(port, timeout=180, idle_timeout=15, max_bytes=32 * 1024 * 1024,
                 clock=time.monotonic, serial_factory=None):
    """Return (bytes, metadata); quiet serial is NOT proof of a complete dump."""
    if serial_factory is None:
        try:
            import serial
        except ImportError as e:
            raise ValueError('USB collection needs pyserial. Run Install.bat once, '
                             'or import a saved serial log.') from e
        serial_factory = serial.Serial
    stream = None
    data = bytearray()
    result = dict(complete=False, port=port, baudrate=115200, verified_nzrt=False)
    try:
        # DTR enables normal CDC output; RTS stays inactive. Do not pulse
        # either line as a reset sequence. USB itself may re-enumerate/reset.
        stream = serial_factory(port=None, baudrate=115200, timeout=0.2,
                                write_timeout=3, rtscts=False, dsrdtr=False)
        stream.dtr = True
        stream.rts = False
        stream.port = port
        stream.open()
        start = clock()
        while clock() - start < 2:
            stream.read(4096)
        stream.write(b'nzrt status\r')
        stream.flush()
        probe = bytearray()
        start = clock()
        while clock() - start < 8:
            probe.extend(stream.read(4096))
            if b'NZRT DIAG build=' in probe and b'\n' in probe.split(b'NZRT DIAG build=',1)[1]:
                result['verified_nzrt'] = True
                break
        result['status_reply'] = probe.decode('utf-8', errors='replace')
        if not result['verified_nzrt']:
            raise ValueError('No NZRT response on this port. Check the device, '
                             'close other Serial Monitors, and try again.')
        # Discard the probe reply, not the stored flash journal. Only the
        # response after the read-only `log` request is archived as the dump.
        stream.write(b'log\r')
        stream.flush()
        start = last = clock()
        tail = b''
        while clock() - start < timeout:
            chunk = stream.read(4096)
            if chunk:
                data.extend(chunk)
                last = clock()
                tail = (tail + chunk)[-8192:]
                if EOF.search(tail):
                    result['complete'] = True
                    break
                if len(data) > max_bytes:
                    result['error'] = 'Journal exceeded the download size limit; retained partial bytes.'
                    break
                if b'Unknown command' in tail:
                    result['error'] = 'Firmware does not support the stored-log command.'
                    break
            elif clock() - last >= idle_timeout:
                result['error'] = 'Timed out waiting for the journal EOF marker; retained partial bytes.'
                break
        if not result['complete'] and 'error' not in result:
            result['error'] = 'Journal download exceeded its time limit; retained partial bytes.'
    except KeyboardInterrupt:
        result['error'] = 'Download interrupted; retained any partial bytes.'
    except Exception as e:
        result['error'] = str(e)
    finally:
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
    return bytes(data), result


def select_port(saved, input_fn=input):
    try:
        from serial.tools import list_ports
    except ImportError as e:
        raise ValueError('Run Install.bat once to add USB serial support (pyserial).') from e
    ports = sorted(list_ports.comports(), key=lambda p: p.device)
    if not ports:
        raise ValueError('No serial ports found. Connect the XiaoRT and try again.')
    preferred = None
    for i, p in enumerate(ports, 1):
        print(f'  {i}. {p.device}: {p.description}  USB serial: {p.serial_number or "unknown"}')
        if (saved.get('serial_number') and p.serial_number == saved['serial_number']) or (
                not saved.get('serial_number') and p.device == saved.get('port')):
            preferred = i
    if preferred is None and len(ports) == 1:
        preferred = 1
    suffix = f' [Enter = {preferred}]' if preferred else ''
    answer = input_fn('Select the XiaoRT port number' + suffix + ', or S to skip: ').strip()
    if answer.lower() in ('s', 'skip', 'esc', '\x1b', 'q'):
        return None
    try:
        index = preferred if not answer else int(answer)
        if index is None or not 1 <= index <= len(ports):
            raise ValueError()
    except ValueError:
        raise ValueError('Choose one of the listed port numbers.')
    return ports[index - 1]


def collection_status(root, day, status, **fields):
    result = dict(day=day, status=status, updated_utc=utc_now(), **fields)
    write_json(root / 'Daily_Run_Reports' / day / 'XiaoRT' / 'collection.json', result)
    return result


def daily_collect(root, day, input_fn=None, interactive=None, config_path=None):
    """Optional once-per-run prompt. All errors are recoverable or skippable."""
    input_fn = input_fn or input
    interactive = sys.stdin.isatty() if interactive is None else interactive
    status_path = root / 'Daily_Run_Reports' / day / 'XiaoRT' / 'collection.json'
    prior = read_json(status_path, {})
    if not interactive:
        return prior or collection_status(root, day, 'not_collected', note='Non-interactive run: USB collection skipped.')
    config_path = config_path or HERE / 'rt_serial.json'
    try:
        saved = read_json(config_path, {})
    except (ValueError, OSError):
        saved = {}
    while True:
        try:
            reusable = prior.get('status') in ('downloaded', 'imported') and (root / prior.get('raw_log', 'MISSING')).is_file()
            if reusable:
                prompt = ('XiaoRT log already archived for this run. Enter to reuse, '
                          'C to collect again, I to import, or S to skip: ')
            else:
                prompt = ('Connect the XiaoRT to USB. Close other Serial Monitors. '
                          'Press Enter when ready, I to import a saved log, or S/ESC then Enter to skip: ')
            answer = input_fn(prompt).strip().lower()
            if not answer and reusable:
                return prior
            if answer in ('s', 'skip', 'esc', '\x1b', 'q'):
                note = input_fn('Optional XiaoRT field note (Enter to leave blank): ').strip()
                return collection_status(root, day, 'skipped', note=note,
                                         previous_raw_log=prior.get('raw_log'))
            if answer == 'i':
                name = input_fn('Path to saved XiaoRT serial log: ').strip().strip('"')
                path, meta = import_log(root, Path(name))
                return collection_status(root, day, 'imported', raw_log=path.relative_to(root).as_posix(),
                    complete=meta['complete'], sha256=meta['sha256'],
                    note='' if meta['complete'] else 'Saved log has no EOF marker; completeness is unknown.')
            port = select_port(saved, input_fn)
            if port is None:
                return collection_status(root, day, 'skipped', note='USB port selection skipped.')
            print('Reading the retained flash journal at 115200 baud. Logs on the device will not be erased.', flush=True)
            data, meta = read_journal(port.device)
            raw_path = None
            if data:
                values = {k: v for k, v in meta.items() if k != 'complete'}
                raw_path, archived = archive_log(root, data, 'serial_log_command', meta['complete'], **values)
            if meta.get('complete'):
                write_json(config_path, dict(port=port.device, serial_number=port.serial_number))
                return collection_status(root, day, 'downloaded', raw_log=raw_path.relative_to(root).as_posix(),
                                         complete=True, sha256=archived['sha256'])
            error = meta.get('error', 'Journal download was incomplete.')
            collection_status(root, day, 'incomplete', error=error,
                              partial_log=raw_path.relative_to(root).as_posix() if raw_path else None)
            print('XiaoRT:', error, 'Enter to retry, I to import, or S to continue the daily run.', flush=True)
        except (EOFError, KeyboardInterrupt):
            print('\nXiaoRT collection skipped; the daily run continues.', flush=True)
            return collection_status(root, day, 'skipped', note='Collection cancelled at the prompt.')
        except Exception as e:
            print('XiaoRT collection:', e, 'Retry, import a saved log, or skip.', flush=True)


def load_archives(root):
    texts, warnings = [], []
    directory = root / 'XiaoRT_Logs' / 'Raw'
    for path in sorted(directory.glob('*.txt')):
        try:
            meta = read_json(path.with_suffix('.json'), {})
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != meta.get('sha256'):
                warnings.append('Archived RT log hash mismatch; excluded: ' + path.name)
                continue
            # Failed USB transfers stay available as evidence, but do not
            # silently inflate counts with an incomplete journal.
            if not meta.get('complete') and meta.get('method') != 'saved_log_import':
                warnings.append('Incomplete USB download excluded: ' + path.name)
                continue
            if not meta.get('complete'):
                warnings.append('Imported terminal log has unknown completeness: ' + path.name)
            texts.append((path.relative_to(root).as_posix(), data.decode('utf-8-sig', errors='replace')))
        except (ValueError, OSError) as e:
            warnings.append(path.name + ': ' + str(e))
    parsed = parse_logs(texts)
    parsed['warnings'] = warnings
    return parsed


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=HERE.parent)
    p.add_argument('--day', help='Recording folder YYYYMMDD; defaults to latest nonempty recorder day')
    p.add_argument('--daily', action='store_true', help='Called from the Daily Run stage')
    p.add_argument('--import-log', type=Path, help='Import an existing saved serial log without a USB prompt')
    p.add_argument('--timeline-only', action='store_true', help='Rebuild reports from already archived logs')
    a = p.parse_args()
    root = a.root.resolve()
    from daily_timeline import report_days, refresh
    days = report_days(root)
    day = a.day or (days[-1] if days else None)
    if not day or not re.fullmatch(r'\d{8}', day):
        p.error('No valid recording day found. Supply --day YYYYMMDD.')
    datetime.strptime(day, '%Y%m%d')
    (root / day).mkdir(parents=True, exist_ok=True)
    if a.import_log:
        path, meta = import_log(root, a.import_log)
        collection_status(root, day, 'imported', raw_log=path.relative_to(root).as_posix(),
                          complete=meta['complete'], sha256=meta['sha256'])
    elif not a.timeline_only:
        daily_collect(root, day)
    cfg = read_json(HERE / 'config.json', {})
    refresh(root, cfg, sorted(set(days + [day])))
    print('Daily timeline:', root / 'Daily_Timeline' / day / 'index.html')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as e:
        print('XiaoRT import:', e, file=sys.stderr)
        sys.exit(1)
