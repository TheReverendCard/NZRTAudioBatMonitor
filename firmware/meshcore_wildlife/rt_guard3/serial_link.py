"""Run the installed GUARD-2 serial diagnostic; no flashing, model or WAV setting edits."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

STAGES = ('capture', 'score', 'send')
BUILD = 'NZRT-J4-GUARD-2'

def fields(line):
    return dict(re.findall(r'\b(\w+)=([^\s]+)', line))

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
                        raise RuntimeError('Board restarted; results from different sessions cannot be combined.')
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

