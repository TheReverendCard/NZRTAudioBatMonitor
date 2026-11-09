#include "WildlifeDetector.h"
#include <cmath>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
namespace WildlifeDetector {
namespace {
// NZ band monitor fast decimator: 3.072 MHz PDM -> 192 kHz PCM.
// First: third-order integer CIC, R=16, gain=4096.
// Second: 17-tap Kaiser anti-alias cleanup FIR at 192 kHz (65 kHz cutoff).
// NOTE: not species identification or a substitute for acoustic validation.
static const float taps[17] = {
 -0.000571507926978f, 0.00223070038605f, 0.00169296469416f,
 -0.0182163567231f, 0.030484138165f, 0.00698446472915f,
 -0.119975907361f, 0.25890005028f, 0.676942907513f,
 0.25890005028f, -0.119975907361f, 0.00698446472915f,
 0.030484138165f, -0.0182163567231f, 0.00169296469416f,
 0.00223070038605f, -0.000571507926978f
};
uint32_t cic_i1=0,cic_i2=0,cic_i3=0,cic_c1=0,cic_c2=0,cic_c3=0;
uint8_t cic_phase=0;
float fir_delay[17]={};
uint8_t fir_head=0;
uint32_t settleSamples=0;
uint64_t rawTimeSamples=0;
// two cascaded 2nd-order Butterworth filters at 192 kHz: HP18k then LP45k
struct Biquad {
 float b0,b1,b2,a1,a2,z1,z2;
 Biquad(float b0_,float b1_,float b2_,float a1_,float a2_)
   : b0(b0_),b1(b1_),b2(b2_),a1(a1_),a2(a2_),z1(0),z2(0) {}
 float step(float x) { float y=b0*x+z1; z1=b1*x-a1*y+z2; z2=b2*x-a2*y; return y; }
};
Biquad hp={0.65745519149f,-1.31491038298f,0.65745519149f,-1.19391336772f,0.43590739824f};
Biquad lp={0.26471264609f,0.52942529219f,0.26471264609f,-0.11506372344f,0.17391430782f};
uint32_t warm=0,samples=0,windows=0,events=0;
float energy=0,noise=0,lastRms=0,maxRatio=0;
bool active=false;
uint32_t firstOn=0,lastOn=0;
float eventPeak=0;
Event backlog[32];
uint8_t eventHead=0,eventTail=0;
portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
void finishWindow() {
 float rms=sqrtf(energy/3840.0f); energy=0; ++windows;
 uint32_t t=static_cast<uint32_t>((rawTimeSamples*1000ULL)/192000ULL); float relative=0;
 if(windows<=150) noise+=(rms-noise)/(float)windows;
 else {
   relative=rms/(noise+1.e-12f);
   bool hot=relative>=1.8f;
   if(hot) {
      if(!active) {active=true;firstOn=t-20;eventPeak=relative;}
      lastOn=t; if(relative>eventPeak)eventPeak=relative;
   } else if(active && t-lastOn>=200) {
      Event e={++events,firstOn,lastOn,eventPeak};
      portENTER_CRITICAL(&mux);
      uint8_t next=(eventHead+1)%32;
      if(next!=eventTail){backlog[eventHead]=e;eventHead=next;}
      portEXIT_CRITICAL(&mux);
      active=false;
   }
   if(!hot&&relative<1.4f)noise+=0.003f*(rms-noise);
 }
 portENTER_CRITICAL(&mux);
 lastRms=rms;if(relative>maxRatio)maxRatio=relative;
 portEXIT_CRITICAL(&mux);
}
}
void reset() {
 for(float &v:fir_delay)v=0;
 cic_i1=cic_i2=cic_i3=cic_c1=cic_c2=cic_c3=0;
 cic_phase=fir_head=0;
 settleSamples=0;
 rawTimeSamples=0;
 hp.z1=hp.z2=lp.z1=lp.z2=0;
 warm=samples=windows=events=0;
 energy=noise=lastRms=maxRatio=0; active=false;firstOn=lastOn=0;eventPeak=0;
 portENTER_CRITICAL(&mux);eventHead=eventTail=0;portEXIT_CRITICAL(&mux);
}
// A missing DMA block invalidates filter continuity, but must not reset
// the background calibration every ~100ms or the detector never starts.
void onInputGap(uint32_t missingBlocks) {
 for(float &v:fir_delay)v=0;
 cic_i1=cic_i2=cic_i3=cic_c1=cic_c2=cic_c3=0;
 cic_phase=fir_head=0;
 hp.z1=hp.z2=lp.z1=lp.z2=0;
 energy=0; samples=0;
 active=false;
 settleSamples=960; // discard 5ms of filter reacquisition
 rawTimeSamples+=static_cast<uint64_t>(missingBlocks)*1024ULL;
}
void consume(const uint8_t* raw,size_t n) {
 // Chronological little-endian 16-bit I2S words, each unpacked MSB first.
 // Integer CIC operations deliberately wrap modulo 32 bits.
 for(size_t i=0;i+1<n;i+=2) {
   uint16_t word=(uint16_t)raw[i]|((uint16_t)raw[i+1]<<8);
   for(int bit=15;bit>=0;--bit) {
     uint32_t v=(word&(1U<<bit))?1U:UINT32_MAX;
     cic_i1+=v;
     cic_i2+=cic_i1;
     cic_i3+=cic_i2;
     if(++cic_phase!=16)continue;
     cic_phase=0;
     uint32_t t1=cic_i3-cic_c1; cic_c1=cic_i3;
     uint32_t t2=t1-cic_c2; cic_c2=t1;
     uint32_t t3=t2-cic_c3; cic_c3=t2;
     float down=(float)((int32_t)t3)*(1.0f/4096.0f);
     fir_delay[fir_head]=down;
     if(++fir_head==17)fir_head=0;
     float pcm=0;uint8_t pos=fir_head;
     for(uint8_t j=0;j<17;++j) {
       pcm+=taps[j]*fir_delay[pos];
       if(++pos==17)pos=0;
     }
     float band=lp.step(hp.step(pcm));
     ++rawTimeSamples;
     if(++warm<=9600)continue;
     if(settleSamples) {--settleSamples;continue;}
     energy+=band*band;
     if(++samples==3840){samples=0;finishWindow();}
   }
 }
}
bool pop(Event& out){
 portENTER_CRITICAL(&mux);
 bool has=eventTail!=eventHead;
 if(has){out=backlog[eventTail];eventTail=(eventTail+1)%32;}
 portEXIT_CRITICAL(&mux);
 return has;
}
void snapshot(Snapshot& out) {
 portENTER_CRITICAL(&mux);
 out={windows,events,lastRms,noise,maxRatio};
 portEXIT_CRITICAL(&mux);
}
}
