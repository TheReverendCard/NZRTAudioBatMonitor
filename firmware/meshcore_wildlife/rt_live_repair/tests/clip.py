"""Host-run the production pre/post-trigger ring with nonaligned boundaries and gaps."""
from pathlib import Path
import tempfile,subprocess
payload=Path(__file__).resolve().parents[1]/'payload'
ml=(payload/'WildlifeML.cpp').read_text()
start=ml[ml.index('constexpr size_t PRE='):ml.index('float* workspace=')]
producer=ml[ml.index('constexpr size_t CHUNK='):ml.index('void tick()')]
code=r"""
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#define portENTER_CRITICAL(x)
#define portEXIT_CRITICAL(x)
""" + start + r"""
std::atomic<bool> enabled{true}, activeMode{false},wavEnabled{true};
std::atomic<uint32_t> skipped{0},gaps{0};
bool mutating=false;
""" + producer + r"""
int main() {
 std::vector<int16_t> hist(PRE),clip0(TOTAL),clip1(TOTAL);
 ring=hist.data();clips[0].pcm=clip0.data();clips[1].pcm=clip1.data();
 auto feed=[](int i){pcm(float(i%1000)/32768.f);};
 trigger(3,1,1);assert(shortHistory==1 && skipped==0);
 for(int i=0;i<55557;++i)feed(i);
 trigger(3,2,1000);assert(clips[0].state==FILLING);
 for(int i=55557;i<55557+TOTAL-PRE+128;++i)feed(i);
 assert(clips[0].state==READY && clips[0].n==TOTAL);
 for(int i=0;i<(int)TOTAL;++i)assert(clip0[i]==(55557-(int)PRE+i)%1000);
 trigger(3,3,2800);feed(7);gap();assert(!clips[1].valid && clips[1].state==READY);
 assert(stagedN==0 && ringN==0 && clips[1].n==PRE+1);
 trigger(3,4,2801);assert(shortHistory==2);
}
"""
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/'test.cpp';p.write_text(code)
    subprocess.run(['c++','-std=c++11','-O2',str(p),'-o',td+'/test'],check=True)
    subprocess.run([td+'/test'],check=True)
print('PASS: exact 384000-sample clip, ring wrap, trigger timing, gap invalidation')
