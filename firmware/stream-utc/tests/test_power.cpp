#include <cassert>
#include <cstdint>
#include <cstdio>
#include "../XiaoStream/wifi_window.h"
#include "../XiaoStream/scorer.h"
#include "../XiaoStream/pulse_train.h"

static void radioTest() {
    WifiWindow w;
    assert(w.shouldStart(0)); w.start(0);
    assert(!w.shouldStop(500,true,false));
    assert(w.shouldStop(900,true,true)); w.stop(900,true);
    assert(!w.shouldStart(3600000));
    w.demand(3600100); assert(w.shouldStart(3600100)); w.start(3600100);
    w.demand(3612100);
    assert(w.shouldStop(3612100,false,true)); w.stop(3612100,false);
    w.demand(3620000); assert(!w.shouldStart(3620000));
    assert(!w.shouldStart(4000000));
    w.demand(4000000); w.start(4000000);
    assert(!w.shouldStop(4000100,true,true));
    assert(w.shouldStop(4000500,true,true)); w.stop(4000500,true);
    assert(w.elapsed(5000000)==13400 && w.starts==3);
    WifiWindow noClock;
    noClock.start(0); assert(noClock.shouldStop(20000,true,false));
    noClock.stop(20000,true); assert(!noClock.shouldStart(86400000));
    assert(wantClockRx(0,false,0) && !wantClockRx(135000,false,0));
    assert(wantClockRx(617000,false,0) && !wantClockRx(3599999,true,0));
    assert(wantClockRx(3600000,true,0) && !wantClockRx(3735000,true,0));
}

// Optional inputs are mono PCM16 192 kHz with the Stream 44-byte WAV header.
int main(int argc,char** argv) {
    radioTest();
    Scorer old,packed;
    old.init(); packed.init(); old.useReference(true);
    uint32_t rng=12345;
    unsigned tested=0, different=0, changed=0;
    for(int file=0;file<argc;++file) {
        old.reset(); packed.reset();
        pulse_train::Detector a,b;
        FILE* f=file?fopen(argv[file],"rb"):nullptr;
        if(file && (!f || fseek(f,44,SEEK_SET)!=0)) return 2;
        for(unsigned frame=0;;++frame) {
            int16_t pcm[512];
            if(f) { if(fread(pcm,sizeof(pcm),1,f)!=1) break; }
            else {
                if(frame==8192) break;
                for(int i=0;i<512;++i) {
                    rng=rng*1664525u+1013904223u;
                    pcm[i]=int16_t(int(rng>>16)-32768)/(1<<(frame/256%14));
                    if(frame%257==0) pcm[i]=0;
                }
            }
            int32_t x=0,y=0;
            bool p=old.evaluate(pcm,x),q=packed.evaluate(pcm,y);
            assert(p==q);
            if(!p) continue;
            ++tested; different+=(x!=y);
            bool pulseA=a.update(x),pulseB=b.update(y);
            changed+=((x>=model::cutoff)!=(y>=model::cutoff) || pulseA!=pulseB);
        }
        if(f) fclose(f);
    }
    printf("%u scored frames, %u numerical differences, %u changed trigger decisions\n",tested,different,changed);
    return changed?1:0;
}
