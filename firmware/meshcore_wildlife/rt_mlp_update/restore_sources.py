"""Restore an update's source backup only. Never flashes or erases a device."""
import json,shutil
from pathlib import Path
from update import sha

def main():
 report=Path(input('Full RT_MLP Update_Reports folder to restore: ').strip().strip('"')).resolve()
 meta=json.loads((report/'backup_manifest.json').read_text());receipt=json.loads((report/'receipt.json').read_text());project=Path(meta['project'])
 backup=report/'source_backup'
 for rel,expected in receipt['installed_hashes'].items():
  p=project/rel
  if not p.is_file() or sha(p)!=expected:raise ValueError('Subsequent edit or missing installed file: '+rel+'. Nothing restored.')
 for rel,expected in meta['backup_hashes'].items():
  if not (backup/rel).is_file() or sha(backup/rel)!=expected:raise ValueError('Backup checksum mismatch: '+rel)
 for rel,was in meta['existed'].items():
  path=project/rel
  if was:shutil.copy2(backup/rel,path)
  else:path.unlink(missing_ok=True)
 marker=project/'RT_MLP_Install.json'
 if (backup/marker.name).exists():shutil.copy2(backup/marker.name,marker)
 else:marker.unlink(missing_ok=True)
 print('Previous sources restored. Device firmware is unchanged. Rebuild/upload explicitly to roll back the device.')
if __name__=='__main__':
 try:main()
 except (Exception,KeyboardInterrupt) as e:print('STOPPED:',e);raise SystemExit(1)
