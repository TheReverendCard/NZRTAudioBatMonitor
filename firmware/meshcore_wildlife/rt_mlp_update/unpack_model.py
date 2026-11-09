"""Restore the numeric model from the repository's text representation."""
import base64,json
from pathlib import Path
from model_tool import validate
root=Path(__file__).resolve().parent/'models';manifest=json.loads((root/'manifest.json').read_text())
data=base64.b64decode((root/'wav_mlp_v01.bin.b64').read_text(),validate=True)
if validate(data)!=manifest['sha256']:raise SystemExit('Model checksum mismatch')
path=root/'wav_mlp_v01.bin'
if path.exists() and path.read_bytes()!=data:raise SystemExit('Refusing to overwrite a different model file')
path.write_bytes(data)
print('Built-in numeric model package verified.')
