#!/usr/bin/env python3
"""Regression check for the field-pilot minute-report printf crash.

FIELD-PILOT-4 once passed a pointer for a %lu and the uptime (60 seconds)
for %s, causing LoadProhibited at EXCVADDR 0x0000003c on Core 1.
Compile checks did not catch it because Serial.printf arguments are varargs.
"""
import re
from pathlib import Path

src = (Path(__file__).resolve().parent / "WildlifeMic.cpp").read_text()
pattern = re.compile(
    r'Serial\.printf\("NZRT MIC session=%08lX t=%lus mode=%s capture=%s '
    r'bps=%lu[^"]*\\n"\s*,\s*'
    r'\(unsigned long\)sessionId\s*,\s*'
    r'static_cast<unsigned long>\(now/1000\)\s*,\s*'
    r'dayStandby\s*\?\s*"DAY_STANDBY"\s*:\s*"MONITORING"\s*,\s*'
    r'captureRunning\s*\?\s*"ON"\s*:\s*"OFF"\s*,\s*'
    r'static_cast<unsigned long>\(bps\)\s*,\s*density\s*,',
    re.MULTILINE,
)
assert pattern.search(src), (
    "NZRT MIC minute-report printf argument order changed. "
    "Check that t=%lu receives uptime, and mode/capture %s receive "
    "text strings; wrong types caused a 60-second crash."
)
print("PASS: NZRT MIC minute report format/argument order")
