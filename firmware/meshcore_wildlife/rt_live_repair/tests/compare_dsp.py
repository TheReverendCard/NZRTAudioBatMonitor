"""Compare PCM for identical PDM at true detector output on the installed and patched paths."""
from pathlib import Path
import array
import math
import subprocess
import tempfile
import time
here=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    fake=folder/'freertos';fake.mkdir()
    (fake/'FreeRTOS.h').write_text('')
    (fake/'portmacro.h').write_text('#define portMUX_TYPE int\n#define portMUX_INITIALIZER_UNLOCKED 0\n#define portENTER_CRITICAL(x)\n#define portEXIT_CRITICAL(x)\n')
    (folder/'WildlifeML.h').write_text('''#include <cstdio>
#include <cstdint>
namespace WildlifeML {
inline void pcm(float x){fwrite(&x,sizeof(x),1,stdout);}
inline void trigger(uint32_t,uint32_t,uint32_t){}
inline void gap(){}}
''')
    samples=[]
    for src in [here.parent/'rt_mlp_update/payload/nzrt/WildlifeDetector.cpp',here/'payload/WildlifeDetector.cpp']:
        (folder/'detector.cpp').write_bytes(src.read_bytes())
        (folder/'main.cpp').write_text(r"""
#include "detector.cpp"
int main(){
  uint32_t state=123;
  WildlifeDetector::reset();
  uint8_t bytes[2048];
  for(unsigned block=0;block<700;++block){
    for(auto& b:bytes){state=state*1664525u+1013904223u;b=state>>24;}
    if(block%127==126)WildlifeDetector::onInputGap(1);
    WildlifeDetector::consume(bytes,sizeof(bytes),0);
  }
}
""")
        subprocess.run(['c++','-std=c++11','-O2','-I'+str(folder),'-I'+str(here.parent/'recovered_snapshot/nzrt'),
                        str(folder/'main.cpp'),'-o',str(folder/'run')],check=True)
        values=array.array('f')
        values.frombytes(subprocess.check_output([str(folder/'run')]))
        samples.append(values)
    assert len(samples[0])==len(samples[1])==716800
    worst=max(abs(a-b) for a,b in zip(*samples))
    assert worst<=1e-6
    print(f'PASS: {len(samples[0])} PCM samples, worst absolute difference {worst:.3g} full scale')
