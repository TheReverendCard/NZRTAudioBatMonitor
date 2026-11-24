#pragma once
#include <stdint.h>
#include <math.h>
#include <string.h>

// GUARD6 RT microphone decoder. DMA stores each MSB-first 16-bit slot little-endian.
class PdmDecoder {
    struct Moment { int a, b, c; } table[256];
    uint32_t i1,i2,i3,c1,c2,c3;
    float delayLine[34]; int head;
    void advance(uint8_t byte) {
        const Moment &m=table[byte];
        i3+=8*i2+36*i1+m.c; i2+=8*i1+m.b; i1+=m.a;
    }
public:
    void reset() { i1=i2=i3=c1=c2=c3=0; head=0; memset(delayLine,0,sizeof delayLine); }
    void init() {
        for(int b=0;b<256;++b) {
            Moment m={};
            for(int bit=7;bit>=0;--bit) { m.a+=(b&(1<<bit))?1:-1; m.b+=m.a; m.c+=m.b; }
            table[b]=m;
        }
        reset();
    }
    int16_t sample(uint16_t slot) {
        static const float taps[]={-.000571507926978f,.00223070038605f,.00169296469416f,
            -.0182163567231f,.030484138165f,.00698446472915f,-.119975907361f,.25890005028f,.676942907513f};
        advance(slot>>8); advance(slot&255);
        uint32_t t1=i3-c1,t2=t1-c2,t3=t2-c3;
        c1=i3; c2=t1; c3=t2;
        delayLine[head+17]=delayLine[head]=int32_t(t3)/4096.f;
        head=(head+1)%17;
        float* w=delayLine+head;
        float x=taps[8]*w[8];
        for(int i=0;i<8;++i) x+=taps[i]*(w[i]+w[16-i]);
        return int16_t(lrintf(fminf(32767,fmaxf(-32768,x*32768.f))));
    }
};
