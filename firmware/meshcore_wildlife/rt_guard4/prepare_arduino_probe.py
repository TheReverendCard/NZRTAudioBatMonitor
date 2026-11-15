"""Emit a real-Arduino integration harness. Never flash this test-only image."""
import argparse,shutil
from pathlib import Path
from modify import HERE,emit

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.exists():raise ValueError('Choose a new test-only directory.')
 emit(a.out/'src')
 for n in ('RTModel.h','RTOverlapReference.h','wav_mlp_model_parameters.h','WildlifeML.h','WildlifeScoring.h'):
  shutil.copy2(HERE/'tests/reference'/n,a.out/'src'/n)
 for f in (HERE/'tests/arduino_probe').iterdir():
  shutil.copy2(f,a.out/f.name if f.name=='platformio.ini' else a.out/'src'/f.name)
 print('TEST HARNESS ONLY, no MeshCore or real time/day scheduler. Do not flash.')
 print('Build with: python -m platformio run -d "'+str(a.out)+'" -e guard4_real_framework_probe')
if __name__=='__main__':main()
