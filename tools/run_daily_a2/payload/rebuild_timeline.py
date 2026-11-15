"""Rebuild only Daily_Timeline outputs from existing recordings and reviews.

No recorder uploads, AviaNZ processing, review annotation edits or model training.
"""
import argparse
from pathlib import Path

import bat_tool
import daily_timeline


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--night', help='NZ noon-to-noon recording-night folder YYYYMMDD')
    ap.add_argument('--all', action='store_true', help='Rebuild all available canonical recorder nights')
    a = ap.parse_args()
    here = Path(__file__).resolve().parent
    root = here.parent
    days = daily_timeline.report_days(root)
    if a.night:
        if a.night not in days:
            raise SystemExit('Recording night not found: '+a.night)
        days = [a.night]
    elif not a.all:
        days = days[-1:]
    if not days:
        raise SystemExit('No canonical recorder nights found in '+str(root))
    config = {**bat_tool.DEFAULTS, **(bat_tool.read_json(here / 'config.json') or {})}
    print('Rebuilding timeline(s) for',len(days),'night(s)', flush=True)
    report = daily_timeline.refresh(root, config, days)
    print('Timeline updated:', root / 'Daily_Timeline' / 'index.html')
    print('RT log completeness diagnostics:',root/'Daily_Timeline'/'rt_archive_diagnostics.json')
    print('Counts:', report['rt_events'],'RT candidates; generated',report['days'],'nightly timeline(s).')
    print('Original recordings, annotations and models were not modified.')


if __name__ == '__main__':
    main()
