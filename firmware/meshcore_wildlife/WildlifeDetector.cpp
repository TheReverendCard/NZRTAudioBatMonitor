#include "WildlifeDetector.h"
#include <cmath>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
namespace WildlifeDetector {
namespace {
// CPU-lean 2-stage 3.072 MHz -> 192 kHz PDM decimator.
// Stage 1: CIC3 R=8, modulo 32-bit integrators, gain 512, 384 kHz output.
// Stage 2: 33-tap Kaiser lowpass (65 kHz at fs=384k), decimate by 2.
// Retains 18-45 kHz acoustic response while reducing FIR work >5x.
static const float taps[33] = {
  -4.49425858938e-05f, -4.94961783277e-05f, 0.000393191743311f, 0.00110122407181f, 0.000428158466129f, -0.00291690083795f, -0.00586045075619f,
  -0.00143326791258f, 0.0116467952073f, 0.0196855834061f, 0.00301663458811f, -0.0360121712238f, -0.0562920498306f, -0.00455951546125f,
  0.127449590003f, 0.274182480888f, 0.338530272826f, 0.274182480888f, 0.127449590003f, -0.00455951546125f, -0.0562920498306f,
  -0.0360121712238f, 0.00301663458811f, 0.0196855834061f, 0.0116467952073f, -0.00143326791258f, -0.00586045075619f, -0.00291690083795f,
  0.000428158466129f, 0.00110122407181f, 0.000393191743311f, -4.94961783277e-05f, -4.49425858938e-05f
};
uint32_t cic_i1=0,cic_i2=0,cic_i3=0,cic_c1=0,cic_c2=0,cic_c3=0;
uint8_t cic_phase=0,fir_phase=0;
float fir_delay[33]={};
uint8_t fir_head=0;
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
 uint32_t t=windows*20; float relative=0;
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
 cic_phase=fir_phase=fir_head=0;
 hp.z1=hp.z2=lp.z1=lp.z2=0;
 warm=samples=windows=events=0;
 energy=noise=lastRms=maxRatio=0; active=false;firstOn=lastOn=0;eventPeak=0;
 portENTER_CRITICAL(&mux);eventHead=eventTail=0;portEXIT_CRITICAL(&mux);
}
void consume(const uint8_t* raw,size_t n) {
 // Chronological little-endian 16-bit words, MSB-first; do not use raw
 // S3 PDM peripheral slot packing. Wrap CIC integrators deliberately.
 for(size_t i=0;i+1<n;i+=2) {
   uint16_t word=(uint16_t)raw[i]|((uint16_t)raw[i+1]<<8);
   for(int bit=15;bit>=0;--bit) {
     uint32_t v=(word&(1U<<bit))?1U:UINT32_MAX; // +1 or -1 modulo-2^32
     cic_i1+=v;
     cic_i2+=cic_i1;
     cic_i3+=cic_i2;
     if(++cic_phase!=8)continue;
     cic_phase=0;
     uint32_t t1=cic_i3-cic_c1; cic_c1=cic_i3;
     uint32_t t2=t1-cic_c2; cic_c2=t1;
     uint32_t t3=t2-cic_c3; cic_c3=t2;
     float down=(float)((int32_t)t3)*(1.0f/512.0f);
     fir_delay[fir_head]=down;
     if(++fir_head==33)fir_head=0;
     if(++fir_phase!=2)continue;
     fir_phase=0;
     float pcm=0;uint8_t pos=fir_head;
     for(uint8_t j=0;j<33;++j) {
       pcm+=taps[j]*fir_delay[pos];
       if(++pos==33)pos=0;
     }
     float band=lp.step(hp.step(pcm));
     if(++warm<=9600)continue;
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
