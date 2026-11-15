"""Serial transport and read-only RT identity checks for GUARD-4 tools."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STAGES = ('capture', 'score', 'send')
BUILD = 'NZRT-J5-GUARD-3'

def fields(line):
    return dict(re.findall(r'\b(\w+)=([^\s]+)', line))

class BoardRestarted(RuntimeError):
    def __init__(self, previous, current, line):
        super().__init__('Board restarted; results from different sessions cannot be combined.')
        self.previous, self.current, self.line = previous, current, line

class Link:
    def __init__(self, port, out):
        self.port, self.out = port, out
        self.pending = bytearray()
        self.session = None

    def send(self, cmd):
        self.out.write('> ' + cmd + '\n')
        self.port.write((cmd+'\r\n').encode('ascii'))
        self.port.flush()

    def line(self, deadline):
        while time.monotonic() < deadline:
            end = self.pending.find(b'\n')
            if end >= 0:
                s = self.pending[:end].decode('utf8','replace').rstrip('\r')
                del self.pending[:end+1]
                self.out.write(s+'\n')
                if self.session and s.startswith(('NZRT ALIVE ', 'NZRT DIAG ', 'NZRT DAY_MODE ')):
                    session = fields(s).get('session')
                    if session and session.lower() != self.session:
                        raise BoardRestarted(self.session, session.lower(), s)
                if s.startswith(('NZRT LOAD ', 'NZRT COMPARE ', 'NZRT LOAD_ML ', 'NZRT LOAD_WAV ')):
                    print(s,flush=True)
                return s
            self.pending.extend(self.port.read(min(4096,self.port.in_waiting or 1)))
            if len(self.pending)>131072 and b'\n' not in self.pending:
                raise RuntimeError('No serial line endings received.')
        raise TimeoutError('Timed out waiting for a board response.')

def wait(link, prefix, seconds):
    limit = time.monotonic()+seconds
    while True:
        line = link.line(limit)
        if line.startswith(prefix): return fields(line)

class IdentityError(RuntimeError):
    def __init__(self, message, report):
        super().__init__(message)
        self.report = report

def identify(link, expected, seconds=45, retry_seconds=5, clock=time.monotonic):
    """Require a live DIAG from the chosen port. Never probe/flash another port.

    Earlier MeshCore CLI readers ignore LF and execute only on CR. Link.send
    uses CRLF, accepted by both the old and repaired parsers. Retry status only;
    do not reset the board, erase logs, or change its operating settings.
    """
    report = {'expected_build': expected, 'status': 'not_confirmed',
              'attempts': 0, 'received_lines': 0, 'observed_build': None,
              'line_ending': 'CRLF'}
    deadline = clock() + seconds
    next_request = clock()
    link.send('')  # terminate an old partial line before our first full command
    while clock() < deadline:
        if clock() >= next_request:
            link.send('nzrt status')
            report['attempts'] += 1
            next_request = clock() + retry_seconds
        try:
            line = link.line(min(deadline, next_request))
        except TimeoutError:
            continue
        report['received_lines'] += 1
        if not line.startswith('NZRT DIAG '):
            continue
        info = fields(line)
        report['observed_build'] = info.get('build')
        if info.get('build') != expected:
            report['status'] = 'different_firmware'
            raise IdentityError('Board reports ' + str(info.get('build', 'unknown')) +
                                '; this step requires ' + expected +
                                '. Nothing uploaded.', report)
        if not re.fullmatch(r'[0-9A-Fa-f]{8}', info.get('session', '')):
            continue  # do not accept a truncated/garbled identity
        report.update(status='confirmed', session=info['session'], identity=info)
        return report
    report['status'] = 'no_status_reply' if report['received_lines'] else 'no_serial_output'
    reason = ('Serial output received, but no complete RT status reply.'
              if report['received_lines'] else 'No serial output received on the selected port.')
    raise IdentityError(reason + ' Nothing uploaded. Check the selected RT port and close other Serial Monitors.', report)

