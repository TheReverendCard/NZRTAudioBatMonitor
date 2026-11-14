"""Exercise actual transport bytes against old/new CLI parser behaviour."""
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import serial_link as wire
import upload_candidate as uploader

BUILD = 'NZRT-J4-GUARD-2'

class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now

class Board:
    def __init__(self, clock, cr_only=True, ready=0, build=BUILD, quiet=False, fragment=4096):
        self.clock, self.cr_only, self.ready = clock, cr_only, ready
        self.build, self.quiet, self.fragment = build, quiet, fragment
        self.pending = bytearray()
        self.line = bytearray()
        self.writes = []
        self.commands = []
        self.port = None
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def open(self): pass
    @property
    def in_waiting(self): return len(self.pending)
    def flush(self): pass
    def write(self, data):
        self.writes.append(data)
        for c in data:
            if c == 10 and self.cr_only: continue
            if c in (10, 13):
                cmd = self.line.decode('ascii'); self.line.clear()
                if cmd: self.commands.append(cmd)
                if cmd == 'nzrt status' and self.clock() >= self.ready and not self.quiet:
                    self.pending.extend(('NZRT DIAG build='+self.build+' session=4717F833 run=1\r\n').encode())
            else: self.line.append(c)
        return len(data)
    def read(self, n):
        self.clock.now += .05
        n = min(n, self.fragment)
        data = bytes(self.pending[:n]); del self.pending[:n]
        return data

class SerialTests(unittest.TestCase):
    def check(self, board):
        log = io.StringIO()
        with patch.object(wire.time, 'monotonic', board.clock):
            result = wire.identify(wire.Link(board, log), BUILD, seconds=20, retry_seconds=4, clock=board.clock)
        return result, log.getvalue()
    def test_lf_bug_and_both_parser_styles(self):
        old = Board(Clock())
        old.write(b'\nnzrt status\n')
        self.assertFalse(old.commands)  # original uploader cannot dispatch a command
        for cr_only in (True, False):
            b = Board(Clock(), cr_only=cr_only)
            result, log = self.check(b)
            self.assertEqual(result['status'], 'confirmed')
            self.assertIn(b'nzrt status\r\n', b.writes)
            self.assertEqual(b.commands, ['nzrt status'])
            self.assertIn('NZRT DIAG', log)
    def test_delayed_cli_retry_and_fragmented_response(self):
        b = Board(Clock(), ready=8, fragment=3)
        result, _ = self.check(b)
        self.assertGreaterEqual(result['attempts'], 3)
        self.assertEqual(result['session'], '4717F833')
        self.assertEqual(set(b.commands), {'nzrt status'})
    def test_unknown_firmware_and_no_reply_rejected(self):
        for b, status in [(Board(Clock(), build='NZRT-J5-GUARD-3'), 'different_firmware'),
                          (Board(Clock(), quiet=True), 'no_serial_output')]:
            with self.assertRaises(wire.IdentityError) as ctx: self.check(b)
            self.assertEqual(ctx.exception.report['status'], status)
    def test_heartbeat_is_not_identity(self):
        b = Board(Clock(), quiet=True)
        b.pending.extend(b'NZRT ALIVE session=4717F833 dsp=ON\r\n')
        with self.assertRaises(wire.IdentityError) as ctx: self.check(b)
        self.assertEqual(ctx.exception.report['status'], 'no_status_reply')
    def test_failure_records_diagnostics(self):
        b = Board(Clock(), build='wrong-board')
        module = types.SimpleNamespace(Serial=lambda **kw: b)
        with tempfile.TemporaryDirectory() as td, patch.object(uploader.time, 'sleep'), patch.object(wire.time, 'monotonic', b.clock):
            with self.assertRaises(ValueError): uploader.check_board(module, 'COM8', Path(td))
            report = json.loads((Path(td)/'identity.json').read_text())
            self.assertEqual(report['status'], 'different_firmware')
            self.assertEqual(report['port'], 'COM8')
            self.assertIn('wrong-board', (Path(td)/'before_serial.txt').read_text())
    def test_main_stops_before_flash_tools_on_identity_failure(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            image = project/'.pio/build'/uploader.ENV/'firmware.bin'
            image.parent.mkdir(parents=True); image.write_bytes(b'test-image')
            (project/'guard3_receipt.json').write_text(json.dumps({'status':'compiled_not_hardware_verified','sources':{},'configuration':{},'image_sha256':uploader.sha(image)}))
            fake_serial = types.ModuleType('serial'); fake_tools = types.ModuleType('serial.tools')
            fake_tools.list_ports = types.SimpleNamespace(comports=lambda: [])
            with patch.dict(sys.modules, {'serial':fake_serial,'serial.tools':fake_tools}), patch.object(sys,'argv',['upload_candidate.py','--project',td,'--port','COM8']), patch.object(uploader,'ensure_merge_script',return_value={'status':'already_fixed'}), patch.object(uploader,'check_board',side_effect=ValueError('not confirmed')), patch.object(uploader.subprocess,'run') as flash:
                with self.assertRaises(ValueError): uploader.main()
                flash.assert_not_called()

if __name__ == '__main__': unittest.main()
