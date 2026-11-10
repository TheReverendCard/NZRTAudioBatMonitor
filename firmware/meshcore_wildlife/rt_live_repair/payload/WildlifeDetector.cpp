#include "WildlifeDetector.h"
#ifndef NZRT_HOST_TEST
#include "WildlifeML.h"
#else
namespace WildlifeML { inline void pcm(float){} inline void gap(){} inline void trigger(uint32_t,uint32_t,uint32_t){} }
#endif
#include <cmath>
#include <atomic>
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
// Contributions of eight MSB-first +/-1 inputs to three cascaded integrators.
struct Moments { int16_t a,b,c; };
Moments moments[256];
void initMoments() {
 static bool ready=false;
 if(ready)return;
 for(unsigned byte=0;byte<256;++byte) {
   int a=0,b=0,c=0;
   for(int bit=7;bit>=0;--bit){a+=((byte>>bit)&1)?1:-1;b+=a;c+=b;}
   moments[byte]={int16_t(a),int16_t(b),int16_t(c)};
 }
 ready=true;
}
inline void advanceByte(uint8_t byte) {
 const Moments& m=moments[byte];
 cic_i3+=8u*cic_i2+36u*cic_i1+m.c;
 cic_i2+=8u*cic_i1+m.b;
 cic_i1+=m.a;
}
float fir_delay[34]={};
uint8_t fir_head=0;
uint32_t settleSamples=0;
uint64_t rawTimeSamples=0;
uint64_t gapWindowStart=0;
unsigned gapsInWindow=0;
uint32_t optionalHoldSamples=0;
std::atomic<uint32_t> holdCount{0};
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
WildlifeScoring::Analyzer scorer;
float pcmWindow[WildlifeScoring::WINDOW],bandWindow[WildlifeScoring::WINDOW];
uint32_t currentRun=0,clockOrigin=0,eventStartUptime=0,eventEndUptime=0;
uint32_t batLikeCount=0,uncertainCount=0,queueLost=0,inputGaps=0;
Event backlog[32];
uint8_t eventHead=0,eventTail=0;
Snapshot published={};
portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
void publish() {
 portENTER_CRITICAL(&mux);
 published={windows,events,lastRms,noise,maxRatio,batLikeCount,uncertainCount,queueLost,inputGaps};
 portEXIT_CRITICAL(&mux);
}
void finishEvent(uint8_t reason) {
 if(!active) return;
 Event e={};
 e.seq=++events;e.start_ms=firstOn;e.end_ms=lastOn;e.peak_ratio=eventPeak;
 e.run=currentRun;e.start_uptime_ms=eventStartUptime;e.end_uptime_ms=eventEndUptime;
 e.features=scorer.finish(eventPeak);e.ended_reason=reason;
 if(e.features.bat_like) ++batLikeCount;else ++uncertainCount;
 portENTER_CRITICAL(&mux);
 uint8_t next=(eventHead+1)%32;
 if(next!=eventTail){backlog[eventHead]=e;eventHead=next;}else ++queueLost;
 portEXIT_CRITICAL(&mux);
 active=false;
}
void finishWindow() {
 float rms=sqrtf(energy/3840.0f); energy=0; ++windows;
 uint32_t t=static_cast<uint32_t>((rawTimeSamples*1000ULL)/192000ULL); float relative=0;
 if(windows<=150) noise+=(rms-noise)/(float)windows;
 else {
   relative=rms/(noise+1.e-12f);
   bool hot=relative>=1.8f;
   if(hot) {
      if(!active) {
        active=true;firstOn=t-20;eventPeak=relative;scorer.reset();
        eventStartUptime=clockOrigin+firstOn;
        WildlifeML::trigger(currentRun,events+1,clockOrigin+t);
      }
      lastOn=t;eventEndUptime=clockOrigin+t;
      if(relative>eventPeak)eventPeak=relative;
   }
   if(active) scorer.window(pcmWindow,bandWindow,noise,hot);
   if(active && !hot && t-lastOn>=200) finishEvent(0);
   // Bounded bouts prevent continuous noise withholding the event forever.
   if(active && t-firstOn>=10000) finishEvent(3);
   if(!hot&&relative<1.4f)noise+=0.003f*(rms-noise);
 }
 lastRms=rms;if(relative>maxRatio)maxRatio=relative;
 publish();
}
void processPcm(float pcm) {
     if(optionalHoldSamples) --optionalHoldSamples;
     else WildlifeML::pcm(pcm);
     float band=lp.step(hp.step(pcm));
     ++rawTimeSamples;
     if(warm<9600){++warm;return;}
     if(settleSamples) {--settleSamples;return;}
     pcmWindow[samples]=pcm;bandWindow[samples]=band;
     energy+=band*band;
     if(++samples==3840){samples=0;finishWindow();}
}

}
void reset(uint32_t run,uint32_t originUptimeMs) {
 initMoments();
 WildlifeML::gap();
 finishEvent(2); // preserve a partial event and the already queued records
 for(float &v:fir_delay)v=0;
 cic_i1=cic_i2=cic_i3=cic_c1=cic_c2=cic_c3=0;
 fir_head=0;
 settleSamples=0;rawTimeSamples=0;
 gapWindowStart=0;gapsInWindow=0;optionalHoldSamples=0;
 hp.z1=hp.z2=lp.z1=lp.z2=0;
 warm=samples=windows=0;
 energy=noise=lastRms=maxRatio=0;active=false;firstOn=lastOn=0;eventPeak=0;
 currentRun=run;clockOrigin=originUptimeMs;
 scorer.reset();publish();
}
// A missing DMA block invalidates filter continuity, but must not reset
// the background calibration every ~100ms or the detector never starts.
void onInputGap(uint32_t missingBlocks) {
 WildlifeML::gap();
 finishEvent(1);++inputGaps;
 // Under repeated loss, spend the next second of contiguous PCM on the
 // primary detector. Keep scoring and recording candidate metadata throughout.
 if(rawTimeSamples-gapWindowStart>=192000){gapWindowStart=rawTimeSamples;gapsInWindow=0;}
 if(++gapsInWindow>=4 || optionalHoldSamples){
   if(!optionalHoldSamples)++holdCount;
   optionalHoldSamples=192000;
 }
 for(float &v:fir_delay)v=0;
 cic_i1=cic_i2=cic_i3=cic_c1=cic_c2=cic_c3=0;
 fir_head=0;
 hp.z1=hp.z2=lp.z1=lp.z2=0;
 energy=0; samples=0;
 active=false;
 settleSamples=960; // discard 5ms of filter reacquisition
 rawTimeSamples+=static_cast<uint64_t>(missingBlocks)*1024ULL;
 publish();
}
void consume(const uint8_t* raw,size_t n,uint32_t captureEndUptimeMs) {
 if(captureEndUptimeMs) {
   // Reader-side timestamp, before queueing. Millisecond estimate with I2S
   // buffering latency, not sample-accurate hardware UTC.
   clockOrigin=captureEndUptimeMs-static_cast<uint32_t>(
      ((rawTimeSamples+n/2)*1000ULL)/192000ULL);
 }
 // Chronological little-endian 16-bit I2S words, each unpacked MSB first.
 // Integer CIC operations deliberately wrap modulo 32 bits.
 for(size_t i=0;i+1<n;i+=2) {
   advanceByte(raw[i+1]);
   advanceByte(raw[i]);
   uint32_t t1=cic_i3-cic_c1; cic_c1=cic_i3;
   uint32_t t2=t1-cic_c2; cic_c2=t1;
   uint32_t t3=t2-cic_c3; cic_c3=t2;
   float down=(float)((int32_t)t3)*(1.0f/4096.0f);
   fir_delay[fir_head]=fir_delay[fir_head+17]=down;
   if(++fir_head==17)fir_head=0;
   const float* window=fir_delay+fir_head;
   float pcm=taps[8]*window[8];
   for(unsigned j=0;j<8;++j)pcm+=taps[j]*(window[j]+window[16-j]);
   processPcm(pcm);
 }
}
#ifdef NZRT_HOST_TEST
// Host replay uses decoded PCM to exercise the real filters/trigger/scorer.
// It does not emulate physical PDM fidelity or ESP32 execution timing.
void consumePcmForTest(const float* pcm,size_t n) {
 for(size_t i=0;i<n;++i) processPcm(pcm[i]);
}
#endif

uint32_t optionalClipHolds(){return holdCount.load();}

bool pop(Event& out){
 portENTER_CRITICAL(&mux);
 bool has=eventTail!=eventHead;
 if(has){out=backlog[eventTail];eventTail=(eventTail+1)%32;}
 portEXIT_CRITICAL(&mux);
 return has;
}
void snapshot(Snapshot& out) {
 portENTER_CRITICAL(&mux);
 out=published;
 portEXIT_CRITICAL(&mux);
}
}
