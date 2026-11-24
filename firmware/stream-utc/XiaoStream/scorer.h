#pragma once
#include <stdint.h>
#include <math.h>
#include <string.h>
#include "model.h"

// Portable radix-2 FFT and the Trial 01 causal band scorer. One call per 512 new PCM samples.
class Scorer {
    static constexpr int N=512;
    float re[N], im[N], win[N], cs[N/2], sn[N/2];
    unsigned reverse[N], cursor=0, count=0;
    bool reference=false;
    float history[8][16];
public:
    void init() {
        for (unsigned i=0;i<N;++i) {
            double angle=6.283185307179586*i/N;
            win[i]=0.5-0.5*cos(angle);
            if (i<N/2) { cs[i]=cos(angle); sn[i]=-sin(angle); }
            unsigned bits=i, rev=0;
            for (int k=0;k<9;++k) { rev=(rev<<1)|(bits&1); bits>>=1; }
            reverse[i]=rev;
        }
        reset();
    }
    void useReference(bool enabled) { reference=enabled; }
    void reset() { count=0; cursor=0; }

private:
    void fft(int size) {
        for (int width=2;width<=size;width*=2) {
            int half=width/2;
            for(int base=0;base<size;base+=width) for(int k=0;k<half;++k) {
                int a=base+k,b=a+half,t=k*(N/width);
                float x=re[b]*cs[t]-im[b]*sn[t], y=re[b]*sn[t]+im[b]*cs[t];
                re[b]=re[a]-x; im[b]=im[a]-y; re[a]+=x; im[a]+=y;
            }
        }
    }
    void referenceBands(const int16_t* pcm) {
        for (int i=0;i<N;++i) { re[reverse[i]]=pcm[i]*win[i]; im[reverse[i]]=0; }
        fft(N);
        for(int b=0;b<16;++b) {
            float energy=0;
            for(int i=model::edges[b];i<model::edges[b+1];++i) energy+=re[i]*re[i]+im[i]*im[i];
            history[cursor][b]=log1pf(energy/(model::edges[b+1]-model::edges[b]));
        }
    }
    // Each complex input packs the even and odd samples of a real signal.
    // Recover only the positive-frequency bins used by the deployed model.
    void packedBands(const int16_t* pcm) {
        constexpr int half=N/2;
        for(int j=0;j<half;++j) {
            unsigned pos=reverse[2*j];
            re[pos]=pcm[2*j]*win[2*j];
            im[pos]=pcm[2*j+1]*win[2*j+1];
        }
        fft(half);
        for(int b=0;b<16;++b) {
            float energy=0;
            for(int k=model::edges[b];k<model::edges[b+1];++k) {
                const int mirror=half-k;
                float dr=re[k]-re[mirror], di=im[k]+im[mirror];
                float x=.5f*(re[k]+re[mirror]+cs[k]*di+sn[k]*dr);
                float y=.5f*(im[k]-im[mirror]+sn[k]*di-cs[k]*dr);
                energy+=x*x+y*y;
            }
            history[cursor][b]=log1pf(energy/(model::edges[b+1]-model::edges[b]));
        }
    }
public:
    bool evaluate(const int16_t* pcm,int32_t& score) {
        if(reference) referenceBands(pcm);
        else packedBands(pcm);
        unsigned newest=cursor; cursor=(cursor+1)%8;
        if (count<8) ++count;
        if (count<8) return false;
        int32_t hidden[12]; memcpy(hidden,model::qb,sizeof(hidden));
        for(int i=0;i<64;++i) {
            float value=history[(newest+8-model::taps[i/16])%8][i%16];
            float z=(value-model::mean[i])/model::std[i];
            int q=lrintf(fminf(127,fmaxf(-127,z/float(model::sx))));
            for(int j=0;j<12;++j) hidden[j]+=q*model::qw[i*12+j];
        }
        score=model::bias;
        for(int j=0;j<12;++j) {
            int q=lrintf(fminf(127,fmaxf(0,hidden[j]*float(model::rescale))));
            score+=q*model::qv[j];
        }
        return true;
    }
};
