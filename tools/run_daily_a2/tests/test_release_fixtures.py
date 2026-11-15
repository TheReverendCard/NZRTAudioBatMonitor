import tempfile,sys,json,types,subprocess,zipfile
from pathlib import Path
import argparse
ap=argparse.ArgumentParser(description='Run against an extracted A1 package and a compatible original BatDailyTool source folder. Fixtures run in a temporary directory.')
ap.add_argument('baseline',type=Path)
baseline=ap.parse_args().baseline.resolve()
package=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(package/'payload'),str(baseline)]
import review_unreviewed_queue as q
from run_integrity import run_lock
with tempfile.TemporaryDirectory() as t:
 root=Path(t);ar=root/'20261106/AR420261106';ar.mkdir(parents=True)
 for i in range(1075):
    p=ar/f'{i:04}.bmp';p.write_bytes(str(i).encode());Path(str(p)+'.data').write_text(json.dumps([{'Duration':1,'Operator':'Auto','Reviewer':q.REVIEWER if i>=1000 else ''}]))
 queue=q.ReviewQueue(root)
 a=queue.prepare();assert a['pending_total']==1075 and a['queue_size']==150
 state=queue.load();priority=[(k,v) for k,v in state['items'].items() if k.startswith('0_')];assert len(priority)==75
 for k,v in priority:
    f=Path(str(queue.active/k)+'.data');hdr=json.loads(f.read_text())[0];hdr['BatDailyReview']=dict(reviewer=q.REVIEWER,source='avianz_gui_hotkey',grade=3);f.write_text(json.dumps([hdr]))
 assert queue.sync()['completed']==75;pending,_=queue.scan();assert len(pending)==1000 and not queue.priority
 k,v=next(iter(queue.load()['items'].items()));f=Path(str(queue.active/k)+'.data');f.write_text(json.dumps([hdr]));original=Path(str(root/v['source'])+'.data');original.write_text('[{"Duration":1,"Reviewer":"someone else"}]');assert len(queue.sync(False)['conflicts'])==1 and 'someone else' in original.read_text()
 with run_lock(root,'test'):
    try:
        with run_lock(root,'other'): assert False
    except RuntimeError:pass
 assert not (root/'.bat_daily_tool.lock').exists()
 print('PASS 1075 inventory, 75 priority in first 150, grade 3 retirement, source conflict and lock ownership')
 tool=root/'BatDailyTool';tool.mkdir()
 import shutil
 for n in ['daily_pipeline.py','daily_timeline.py','annotation_care.py','rt_logs.py']:shutil.copy2(baseline/n,tool/n)
 shutil.copy2(baseline/'review_unreviewed_queue.py',tool/'review_unreviewed_queue.py')
 (tool/'Run Daily Scan.bat').write_text('rem local custom launcher');(tool/'config.json').write_text('{}')
 install=[sys.executable,str(package/'install.py'),'--root',str(root)]
 subprocess.run(install,check=True);assert not (root/'Tool_Backups').exists()
 subprocess.run(install+['--apply'],check=True);subprocess.run(install+['--apply'],check=True)
 backups=sorted((root/'Tool_Backups').glob('*/before.zip'));assert len(backups)==2
 with zipfile.ZipFile(backups[0]) as z:assert z.read('BatDailyTool/daily_pipeline.py')==(baseline/'daily_pipeline.py').read_bytes();assert z.testzip() is None
 subprocess.run([sys.executable,str(package/'restore.py'),str(backups[0])],check=True)
 assert (tool/'daily_pipeline.py').read_bytes()==(baseline/'daily_pipeline.py').read_bytes() and not (tool/'run_integrity.py').exists()
 from external_inventory import register
 pending_before=[rel for _,rel in queue.scan()[0]]
 south=root/'External Data/Mara Kokotoha/South/20261106';south.mkdir(parents=True)
 for n in ('A','B'):(south/(n+'.bmp')).write_bytes(b'common')
 from unittest.mock import patch
 with patch('external_inventory.time.time',return_value=1000):register(root)
 with patch('external_inventory.time.time',return_value=1010):register(root)
 x=json.loads((root/'Daily_Run_Reports/External_Inventory/latest.json').read_text());assert x['sources']['south-ar4']['distinct_hashes']==1 and x['sources']['south-ar4']['verified']==2
 assert [rel for _,rel in queue.scan()[0]]==pending_before
 import annotation_care as care
 bmp=ar/'0001.bmp'; saved=care.machine_snapshot(bmp,engine='fixture',origin='fresh',batch_id='x')
 assert saved['status']=='created'
 side=Path(str(bmp)+'.data');b=Path(saved['backup']);before=b.read_bytes()
 side.write_text('[{"Duration":1}]')
 assert care.machine_snapshot(bmp,engine='fixture',origin='fresh')['status']=='existing_baseline_preserved' and b.read_bytes()==before
 b.write_bytes(before+b' ')
 try:care.machine_snapshot(bmp,engine='fixture',origin='fresh');raise AssertionError()
 except ValueError:pass
 print('PASS immutable machine baseline and tamper detection')
 print('PASS rollback and independent external inventory, repeated scans, alias hash, South excluded')
 (tool/'daily_pipeline.py').write_text('# private hotfix\n')
 r=subprocess.run(install+['--apply']);assert r.returncode and (tool/'daily_pipeline.py').read_text()=='# private hotfix\n'
 print('PASS backup/verified install/reinstall/mismatch guard')
