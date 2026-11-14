import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from merge_upload_fix import ensure_merge_script, OLD_IMPORT, NEW_IMPORT

ORIGINAL = (ROOT/'tests/reference/merge-bin.py').read_bytes()

class MergeTests(unittest.TestCase):
    def test_only_unused_import_changed_with_exact_backup_and_repeat(self):
        for content in (ORIGINAL, ORIGINAL.replace(b'\n', b'\r\n')):
            with tempfile.TemporaryDirectory() as td:
                root = Path(td); p = root/'merge-bin.py'; p.write_bytes(content)
                (root/'firmware.bin').write_bytes(b'unchanged compiled image')
                receipt = ensure_merge_script(root)
                self.assertEqual(Path(receipt['backup']).read_bytes(), content)
                self.assertEqual(p.read_bytes(), content.replace(OLD_IMPORT, NEW_IMPORT))
                self.assertEqual((root/'firmware.bin').read_bytes(), b'unchanged compiled image')
                self.assertEqual(ensure_merge_script(root)['status'], 'already_fixed')
                self.assertEqual(len(list((root/'PreUpdate_Backup').iterdir())), 1)
    def test_unknown_script_not_modified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root/'merge-bin.py'; p.write_bytes(ORIGINAL+b'\n# custom change\n')
            before = p.read_bytes()
            with self.assertRaises(ValueError): ensure_merge_script(root)
            self.assertEqual(p.read_bytes(), before)
            self.assertFalse((root/'PreUpdate_Backup').exists())
    def test_failed_replace_preserves_original_and_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); p = root/'merge-bin.py'; p.write_bytes(ORIGINAL)
            with patch('merge_upload_fix.os.replace', side_effect=OSError('write refused')), self.assertRaises(OSError): ensure_merge_script(root)
            self.assertEqual(p.read_bytes(), ORIGINAL)
            self.assertEqual(next((root/'PreUpdate_Backup').glob('*/merge-bin.py')).read_bytes(), ORIGINAL)
            self.assertFalse((root/'merge-bin.py.guard3_fix.tmp').exists())
    @unittest.skipUnless(importlib.util.find_spec('SCons'), 'Optional real SCons integration requires SCons 4.8.1')
    def test_real_scons_nobuild_import_failure_then_fixed_upload_dispatch(self):
        # Actual SCons import engine, with only the small PlatformIO environment
        # methods adapted. No device, esptool or firmware compile is involved.
        script = '''
env = Environment(tools=[])
env.Replace(BUILD_DIR='.', PROGNAME='firmware')
env.AddMethod(lambda env: {}, 'BoardConfig')
def custom(env, **kw):
    return env.Alias(kw['name'], kw['dependencies'], kw['actions'])
env.AddMethod(custom, 'AddCustomTarget')
Export('env')
if ARGUMENTS.get('normal') == '1':
    projenv = env.Clone()
    Export('projenv')
SConscript('merge-bin.py', exports='env')
env.Alias('nobuild', [])
def dry_upload(target, source, env):
    print('UPLOAD_DRY_RUN_ONLY')
env.AlwaysBuild(env.Alias('upload', [], dry_upload))
'''
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'merge-bin.py').write_bytes(ORIGINAL)
            (root/'SConstruct').write_text(script)
            image = root/'firmware.bin'; image.write_bytes(b'compiled-image-sentinel')
            before = hashlib.sha256(image.read_bytes()).hexdigest()
            args = [sys.executable, '-m', 'SCons', '-Q', 'nobuild', 'upload']
            fail = subprocess.run(args, cwd=td, capture_output=True, text=True)
            self.assertNotEqual(fail.returncode, 0)
            self.assertIn('projenv', fail.stdout+fail.stderr)
            self.assertNotIn('UPLOAD_DRY_RUN_ONLY', fail.stdout)
            ensure_merge_script(root)
            for mode in ([], ['normal=1']):
                ok = subprocess.run(args+mode, cwd=td, capture_output=True, text=True)
                self.assertEqual(ok.returncode, 0, ok.stdout+ok.stderr)
                self.assertIn('UPLOAD_DRY_RUN_ONLY', ok.stdout)
            self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), before)

if __name__ == '__main__': unittest.main()
