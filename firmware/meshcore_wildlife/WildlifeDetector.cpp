#include "WildlifeDetector.h"
#include <cmath>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
namespace WildlifeDetector {
namespace {
// 97-tap Kaiser FIR 65 kHz low-pass at 3.072 MHz, decimated 16:1 to 192 kHz.
// coefficients from scipy.signal.firwin(97,65000,fs=3072000,window=('kaiser',9))
static const float taps[97] = {
  6.0860861205e-7f, -4.4668540013e-7f, -0.0000037574285100f, -0.000010659231078f, -0.000022785862442f, -0.000042027100988f, -0.000070448662506f, -0.00011017000465f,
  -0.00016319802389f, -0.00023121744263f, -0.00031534191366f, -0.00041583338421f, -0.00053180085562f, -0.00066089310957f, -0.00079900298837f, -0.00094000315520f,
  -0.0010755346730f, -0.0011948700174f, -0.0012848711169f, -0.0013300606040f, -0.0013128206508f, -0.0012137286283f, -0.0010120325490f, -0.00068626207717f,
  -0.00021496316712f, 0.00042246348017f, 0.0012448475209f, 0.0022682918142f, 0.0035052127692f, 0.0049634218896f, 0.0066452941612f, 0.0085470686232f,
  0.010658323783f, 0.012961665437f, 0.015432657122f, 0.018040014012f, 0.020746070168f, 0.023507516861f, 0.026276397187f, 0.029001329599f,
  0.031628921391f, 0.034105322808f, 0.036377864308f, 0.038396713690f, 0.040116487030f, 0.041497747585f, 0.042508330250f, 0.043124435654f,
  0.043331447162f, 0.043124435654f, 0.042508330250f, 0.041497747585f, 0.040116487030f, 0.038396713690f, 0.036377864308f, 0.034105322808f,
  0.031628921391f, 0.029001329599f, 0.026276397187f, 0.023507516861f, 0.020746070168f, 0.018040014012f, 0.015432657122f, 0.012961665437f,
  0.010658323783f, 0.0085470686232f, 0.0066452941612f, 0.0049634218896f, 0.0035052127692f, 0.0022682918142f, 0.0012448475209f, 0.00042246348017f,
  -0.00021496316712f, -0.00068626207717f, -0.0010120325490f, -0.0012137286283f, -0.0013128206508f, -0.0013300606040f, -0.0012848711169f, -0.0011948700174f,
  -0.0010755346730f, -0.00094000315520f, -0.00079900298837f, -0.00066089310957f, -0.00053180085562f, -0.00041583338421f, -0.00031534191366f, -0.00023121744263f,
  -0.00016319802389f, -0.00011017000465f, -0.000070448662506f, -0.000042027100988f, -0.000022785862442f, -0.000010659231078f, -0.0000037574285100f, -4.4668540013e-7f,
  6.0860861205e-7f
};
// two cascaded 2nd-order Butterworth filters at 192 kHz: HP18k then LP45k
struct Biquad {
 float b0,b1,b2,a1,a2,z1,z2;
 Biquad(float b0_,float b1_,float b2_,float a1_,float a2_)
   : b0(b0_),b1(b1_),b2(b2_),a1(a1_),a2(a2_),z1(0),z2(0) {}
 float step(float x) { float y=b0*x+z1; z1=b1*x-a1*y+z2; z2=b2*x-a2*y; return y; }
};
Biquad hp={0.65745519149f,-1.31491038298f,0.65745519149f,-1.19391336772f,0.43590739824f};
Biquad lp={0.26471264609f,0.52942529219f,0.26471264609f,-0.11506372344f,0.17391430782f};
float delay[97]={};
uint8_t head=0,phase=0;
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
 for(float &v:delay)v=0;
 hp.z1=hp.z2=lp.z1=lp.z2=0;
 head=phase=0;warm=samples=windows=events=0;
 energy=noise=lastRms=maxRatio=0; active=false;firstOn=lastOn=0;eventPeak=0;
 portENTER_CRITICAL(&mux);eventHead=eventTail=0;portEXIT_CRITICAL(&mux);
}
void consume(const uint8_t* raw,size_t n) {
 // Chronological little-endian 16-bit words, MSB-first inside each word.
 // Do not silently change to ESP32-S3 native raw PDM peripheral packing.
 for(size_t i=0;i+1<n;i+=2) {
   uint16_t word=(uint16_t)raw[i]|((uint16_t)raw[i+1]<<8);
   for(int bit=15;bit>=0;--bit) {
     delay[head]=(word&(1U<<bit))?1.f:-1.f;
     if(++head==97)head=0;
     if(++phase!=16)continue;
     phase=0;
     float pcm=0;uint8_t pos=head;
     for(uint8_t j=0;j<97;++j) {pcm+=taps[j]*delay[pos];if(++pos==97)pos=0;}
     float band=lp.step(hp.step(pcm));
     if(++warm<=9600)continue; // discard first 50ms of IIR startup
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
