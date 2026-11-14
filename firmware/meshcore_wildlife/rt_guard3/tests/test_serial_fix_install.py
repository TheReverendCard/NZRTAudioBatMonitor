import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import apply_serial_fix as fix

class InstallTests(unittest.TestCase):
    def fixture(self, root):
        target, payload = root/'existing', root/'payload'
        target.mkdir(); payload.mkdir()
        (target/'prepare_build.py').write_text('original build tool')
        (target/'last_candidate.txt').write_text('private compiled project')
        old, new = {}, {}
        for n in fix.OLD:
            (target/n).write_bytes(b'old\r\n')
            (payload/n).write_bytes(b'new\n')
            old[n] = fix.digest(b'old\n'); new[n] = fix.digest(b'new\n')
        (payload/'serial_fix_manifest.json').write_text(json.dumps({'files':new}))
        return target, payload, old
    def test_backup_preservation_and_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            target, payload, old = self.fixture(Path(td))
            with patch.object(fix, 'OLD', old):
                backup = fix.apply(target, payload)
                self.assertEqual((backup/'upload_candidate.py').read_bytes(), b'old\r\n')
                self.assertEqual((target/'last_candidate.txt').read_text(), 'private compiled project')
                self.assertEqual((target/'prepare_build.py').read_text(), 'original build tool')
                self.assertIsNone(fix.apply(target, payload))
    def test_unknown_rejected_before_backup_or_writes(self):
        with tempfile.TemporaryDirectory() as td:
            target, payload, old = self.fixture(Path(td))
            (target/'serial_link.py').write_text('custom edits')
            with patch.object(fix, 'OLD', old), self.assertRaises(ValueError): fix.apply(target, payload)
            self.assertEqual((target/'upload_candidate.py').read_bytes(), b'old\r\n')
            self.assertFalse((target/'Tool_Backups').exists())
    def test_second_write_failure_restores_first(self):
        with tempfile.TemporaryDirectory() as td:
            target, payload, old = self.fixture(Path(td))
            replace = fix.os.replace
            calls = []
            def fail_second(src, dst):
                calls.append(dst)
                if len(calls) == 2: raise OSError('simulated write failure')
                return replace(src, dst)
            with patch.object(fix, 'OLD', old), patch.object(fix.os, 'replace', side_effect=fail_second), self.assertRaises(OSError): fix.apply(target, payload)
            for n in old: self.assertEqual((target/n).read_bytes(), b'old\r\n')
            self.assertEqual(json.loads(next((target/'Tool_Backups').glob('*/receipt.json')).read_text())['status'], 'rolled_back')

if __name__ == '__main__': unittest.main()
