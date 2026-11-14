"""Exercise the optional receiver's actual GET dispatch against a disposable queue."""
import json,sys,tempfile,threading,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'optional_receiver'))
from receiver_extension import extended_handler
class Base:
 def reply(self,status,body):self.answer=status,body
with tempfile.TemporaryDirectory() as td:
 root=Path(td);folder=root/'RT_Controls';folder.mkdir()
 cls=extended_handler(types.SimpleNamespace(Handler=Base),root)
 h=object.__new__(cls);h.server=types.SimpleNamespace(root=root,tokens=['local-test'],commit_lock=threading.Lock())
 h.path='/guard2-version';h.headers={};h.do_GET();assert h.answer[0]==401
 h.headers={'Authorization':'Bearer local-test'};h.do_GET();assert h.answer==(200,'GUARD-2')
 h.path='/rt-control/0123456789ab'
 for cmd,expected in [('pass assist evolved off',200),('pass assist audible off',200),('pass legacy off',200),('pass assist bogus off',422)]:
  (folder/'0123456789ab.json').write_text(json.dumps({'id':'1'*32,'command':cmd}));h.do_GET()
  assert h.answer[0]==expected
print('PASS receiver delivers old and new selections only after authentication')
