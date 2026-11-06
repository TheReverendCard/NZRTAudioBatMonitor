import hashlib,json,shutil,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]));import update
class UpdaterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  candidates=list(Path('upload').glob('*'))+[Path('wifi_work/compile_project')/r for r in json.loads((update.HERE/'baseline_sources.json').read_text())]
  index={update.sha(p):p for p in candidates if p.is_file()}
  for rel,h in json.loads((update.HERE/'baseline_sources.json').read_text()).items():
   if h not in index:raise AssertionError('Test fixture unavailable: '+rel)
   p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(index[h],p)
 def tearDown(self):self.tmp.cleanup()
 def test_prepare_and_repeat(self):
  changes=update.prepare(self.root)
  self.assertIn('nzrt/WildlifeML.cpp',changes);self.assertIn(b'BOARD_HAS_PSRAM',changes['platformio.local.ini'])
  self.assertFalse((self.root/'nzrt/WildlifeML.cpp').exists())
  for rel,data in changes.items():p=self.root/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
  update.write_json(self.root/'RT_MLP_Install.json',{'installed_hashes':{r:update.sha(self.root/r) for r in changes}})
  again=update.prepare(self.root);self.assertEqual(changes,again)
 def test_changed_source_refused(self):
  p=self.root/'nzrt/WildlifeMic.cpp';p.write_bytes(p.read_bytes()+b'\n// changed')
  with self.assertRaises(ValueError):update.prepare(self.root)
  self.assertFalse((self.root/'nzrt/WildlifeML.cpp').exists())
if __name__=='__main__':unittest.main()
