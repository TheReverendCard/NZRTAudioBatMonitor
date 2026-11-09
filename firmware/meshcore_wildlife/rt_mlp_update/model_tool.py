"""Stage a numeric MLP package. Never loads pickle/joblib or executes model code."""
import argparse,hashlib,json,math,struct,shutil
from pathlib import Path
COUNT=6187;SIZE=24+COUNT*4
ROOT=Path(__file__).resolve().parent.parent

def validate(data):
 if len(data)!=SIZE:raise ValueError('Incorrect model length')
 magic,schema,count,threshold,feature=struct.unpack('<8sIIfI',data[:24])
 if magic!=b'NZRTMLP1' or (schema,count,feature)!=(1,COUNT,1):raise ValueError('Unsupported architecture/feature schema')
 values=struct.unpack('<6187f',data[24:])
 if not 0<threshold<1 or not all(math.isfinite(x) for x in values) or any(x<1e-12 for x in values[165:330]):raise ValueError('Invalid model parameters')
 return hashlib.sha256(data).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('model',nargs='?',type=Path);args=ap.parse_args()
 path=args.model or Path(input('Path to exported .bin model: ').strip().strip('"'))
 data=path.read_bytes();sha=validate(data);dest=ROOT/'Models'/'RT'/(sha+'.bin');dest.parent.mkdir(parents=True,exist_ok=True)
 if dest.exists() and dest.read_bytes()!=data:raise ValueError('Conflicting model file')
 temp=dest.with_suffix('.tmp');temp.write_bytes(data);temp.replace(dest)
 print('Staged:',dest);print('On RT serial, request the WiFi download with:');print('nzrt model fetch '+sha)
 print('It installs only during daytime standby when buffers are empty, and starts in shadow mode.')
if __name__=='__main__':main()
