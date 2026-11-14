"""Test exact PASS-1 / GUARD-1 staging and source rejection without PlatformIO or hardware."""
import tempfile
from pathlib import Path
from prepare_build import stage,ENV
from modify import HERE,BASE,guard1
with tempfile.TemporaryDirectory() as td:
 root=Path(td)
 for ver in [1,2]:
  src=root/str(ver);src.mkdir();nz=src/'nzrt';nz.mkdir()
  (src/'platformio.ini').touch();(src/'platformio.local.ini').write_text(f'[env:{ENV}]')
  for n in BASE:
   original=(HERE/'base'/n).read_text()
   (nz/n).write_text(original if ver==1 else guard1(n,original))
  if ver==2:
   for n in ('GuardSignals.h','GuardPolicy.h'):(nz/n).write_bytes((HERE/n).read_bytes())
  stage(src,root/('out'+str(ver)))
 assert all((root/'out1/nzrt'/n).read_bytes()==(root/'out2/nzrt'/n).read_bytes() for n in BASE)
 (nz/'WildlifeML.cpp').write_text('unknown')
 try:stage(src,root/'bad')
 except ValueError:assert not (root/'bad').exists()
 else:raise AssertionError('accepted unknown source')
print('PASS both known source trees generate identical firmware; unknown tree rejected before copy')
