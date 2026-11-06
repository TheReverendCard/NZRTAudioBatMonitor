"""Convert a trusted trainer's numeric NPZ export to the fixed RT MLP format.
NPZ loading uses allow_pickle=False. Architecture/schema changes are rejected.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from model_tool import validate
FEATURE_SHA='27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923'
SHAPES={'mean':(165,),'scale':(165,),'w0':(165,32),'b0':(32,),'w1':(32,16),'b1':(16,),'w2':(16,1),'b2':(1,)}
def export(source,threshold,destination):
 if not 0<threshold<1:raise ValueError('Threshold must be between zero and one')
 with np.load(source,allow_pickle=False) as pack:
  if str(pack['feature_source_sha256'].item())!=FEATURE_SHA:raise ValueError('Feature schema changed; retraining export needs a new firmware extractor')
  if list(pack['classes'])!=[0,1]:raise ValueError('Class order must be [0,1]')
  arrays=[]
  for key,shape in SHAPES.items():
   v=np.asarray(pack[key],dtype='<f4')
   if v.shape!=shape:raise ValueError('Wrong shape for '+key)
   arrays.append(v.tobytes(order='C'))
 data=struct.pack('<8sIIfI',b'NZRTMLP1',1,6187,threshold,1)+b''.join(arrays);sha=validate(data)
 destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
 destination.with_suffix('.json').write_text(json.dumps({'schema':1,'sha256':sha,'feature_source_sha256':FEATURE_SHA,'source_npz_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'threshold':threshold,'architecture':[165,32,16,1],'initial_mode':'shadow'},indent=2)+'\n')
 return sha
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('npz',type=Path);ap.add_argument('--threshold',type=float,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();print(export(a.npz,a.threshold,a.output))
