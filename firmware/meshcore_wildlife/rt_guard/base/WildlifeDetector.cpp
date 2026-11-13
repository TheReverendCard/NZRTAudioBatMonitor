#include "WildlifeDetector.h"
#ifndef NZRT_HOST_TEST
#include "WildlifeML.h"
#include <esp_timer.h>
namespace WildlifeML {
 bool passCaptureBusy();
 unsigned compareStage();
 const char* clipRequest();
 uint32_t clipOwnerSeq();
 bool benchActive();
 int16_t* testBlock(uint32_t,size_t,size_t&);
 void finishTestBlock(size_t);
 void testGap(uint32_t);
 void endTestStream();
}
#else
namespace WildlifeML { inline uint32_t clipOwnerSeq(){return 0;} inline const char* clipRequest(){return "host";} inline bool benchActive(){return false;} inline void pcm(float){} inline void gap(){} inline void trigger(uint32_t,uint32_t,uint32_t){} }
#endif
#include <cmath>
#include <new>
#include <cstdio>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/portmacro.h>
namespace WildlifeDetector {
// PASS-1. Continuous 192 kHz PCM, reset the feature history at each input gap.
namespace FirstPass {
struct Band {
 float b,a1,a2,z1=0,z2=0;
 Band(float lo,float hi){
   const float f=sqrtf(lo*hi), w=6.28318530718f*f/192000.f;
   const float a=sinf(w)*(hi-lo)/(2*f);
   b=a/(1+a);a1=-2*cosf(w)/(1+a);a2=(1-a)/(1+a);
 }
 inline float step(float x){float y=b*x+z1;z1=z2-a1*y;z2=-b*x-a2*y;return y;}
};
Band bands[]={{18000,24000},{24000,27000},{27000,33000},{36000,44500}};
float background[4],energy[4];
unsigned warmE=0;
bool evolved(const float* pcm){
 bool hot=false;
 for(unsigned start=0;start<3840;start+=1920){
   for(unsigned k=0;k<4;++k){
     float sum=0;auto& b=bands[k];
     for(unsigned i=start;i<start+1920;++i){float y=b.step(pcm[i]);sum+=y*y;}
     energy[k]=sum/1920.f;
   }
   if(warmE<5){++warmE;for(unsigned k=0;k<4;++k)background[k]+=(energy[k]-background[k])/warmE;continue;}
   float x[4];
   for(unsigned k=0;k<4;++k){
     x[k]=fminf(8,energy[k]/(background[k]+1.e-12f))-1;
     background[k]+=.05f*(energy[k]-background[k]);
   }
   float pos=fmaxf(0,-3*x[0]-2*x[1]+x[2]+3*x[3]-.5f);
   float neg=fmaxf(0,-5*x[0]+2*x[1]+2.5f);
   hot|=pos-neg>1;
 }
 return hot;
}
// 960-point mixed-radix DFT. Only allocated when the audible rule is enabled.
struct Complex {float r,i;};
struct Audible {
 Complex roots[960],out[960];
 float window[960],input[960],bg[2]={};
 unsigned warm=0;
 Audible(){
   for(int j=0;j<960;++j){float a=-6.28318530718f*j/960;roots[j]={cosf(a),sinf(a)};
     window[j]=.5f-.5f*cosf(6.28318530718f*j/959);}
 }
 void transform(Complex* dest,int n,int stride,const float* src){
   if(n==1){*dest={*src,0};return;}
   int radix=n%4==0?4:n%3==0?3:5, m=n/radix;
   for(int t=0;t<radix;++t) transform(dest+t*m,m,stride*radix,src+t*stride);
   for(int k=0;k<m;++k){
     Complex v[5];for(int t=0;t<radix;++t)v[t]=dest[k+t*m];
     for(int j=0;j<radix;++j){
       int inc=(k+j*m)*stride,phase=0;Complex s=v[0];
       for(int t=1;t<radix;++t){phase+=inc;if(phase>=960)phase-=960;
         const auto c=roots[phase];s.r+=v[t].r*c.r-v[t].i*c.i;s.i+=v[t].r*c.i+v[t].i*c.r;}
       dest[k+j*m]=s;
     }
   }
 }
 bool check(const float* pcm){
   bool hot=false;
   for(int start=0;start<3840;start+=960){
     for(int i=0;i<960;++i)input[i]=pcm[start+i]*window[i];
     transform(out,960,1,input);
     float a=0,u=0;
     for(int i=10;i<75;++i)a+=out[i].r*out[i].r+out[i].i*out[i].i;
     for(int i=90;i<225;++i)u+=out[i].r*out[i].r+out[i].i*out[i].i;
     a/=65;u/=135;
     if(warm<10){++warm;bg[0]+=(a-bg[0])/warm;bg[1]+=(u-bg[1])/warm;continue;}
     float ar=(a+1.e-12f)/(bg[0]+1.e-12f),ur=(u+1.e-12f)/(bg[1]+1.e-12f);
     hot|=ur>=3.235937f && (ar<1.995262f || ur>=ar*3.981072f);
     bg[0]+=.024690088f*(a-bg[0]);bg[1]+=.024690088f*(u-bg[1]);
   }
   return hot;
 }
};
std::atomic<Audible*> audible{nullptr};
void clear(){warmE=0;for(auto& b:bands)b.z1=b.z2=0;
 if(auto p=audible.load()){p->warm=0;p->bg[0]=p->bg[1]=0;}}
}

constexpr unsigned DEFAULT_PASS=8; // low two bits active, next two shadow (0=off,1=legacy,2=evolved,3=audible for shadow); active 0=legacy,1=evolved,2=audible
std::atomic<unsigned> desiredPass{DEFAULT_PASS}, appliedPass{DEFAULT_PASS};
std::atomic<unsigned> passWindows{0},shadowHot{0},activeHot{0},shadowOnly{0},lastPassUs{0},maxPassUs{0};
unsigned eventPass=DEFAULT_PASS;bool eventShadow=false;
const char* passName(unsigned n){return n==0?"legacy":n==1?"evolved":"audible";}
bool preparePass(unsigned cfg){
 if((cfg&3)>2 || cfg>14 || (cfg>>2)==(cfg&3)+1)return false;
 if(((cfg&3)==2 || (cfg>>2)==3) && !FirstPass::audible.load()){
   auto* p=new(std::nothrow) FirstPass::Audible;
   if(!p)return false;
   FirstPass::audible.store(p);
 }
 return true;
}
bool requestPass(unsigned cfg){
 if(!preparePass(cfg))return false;desiredPass.store(cfg);return true;
}
void passStatus(char* buf,size_t n){
 unsigned cfg=appliedPass.load(),want=desiredPass.load();
 snprintf(buf,n,"NZRT FIRST_PASS version=PASS-1 active=%s shadow=%s requested_active=%s requested_shadow=%s supported=legacy,evolved,audible windows=%u active_hot=%u shadow_hot=%u shadow_only=%u last_us=%u worst_us=%u",
 passName(cfg&3),(cfg>>2)?passName((cfg>>2)-1):"off",passName(want&3),(want>>2)?passName((want>>2)-1):"off",
 passWindows.load(),activeHot.load(),shadowHot.load(),shadowOnly.load(),lastPassUs.load(),maxPassUs.load());
}
unsigned passCurrent(){return appliedPass.load();}
bool passApplied(unsigned cfg){return appliedPass.load()==cfg;}

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
bool active=false,eventBench=false;
uint32_t eventClipOwner=0;
const char* eventClip="unavailable";
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
 e.passConfig=eventPass;e.shadowMatched=eventShadow;
 e.seq=++events;e.start_ms=firstOn;e.end_ms=lastOn;e.peak_ratio=eventPeak;
 e.run=currentRun;e.start_uptime_ms=eventStartUptime;e.end_uptime_ms=eventEndUptime;
 e.features=scorer.finish(eventPeak);e.ended_reason=reason;e.clipRequest=eventClip;e.clipOwnerSeq=eventClipOwner;e.bench=eventBench;
 if(e.features.bat_like) ++batLikeCount;else ++uncertainCount;
 portENTER_CRITICAL(&mux);
 uint8_t next=(eventHead+1)%32;
 if(next!=eventTail){backlog[eventHead]=e;eventHead=next;}else ++queueLost;
 portEXIT_CRITICAL(&mux);
 active=false;
}
static bool measureScore=false;
static uint32_t scoreUs=0;
void finishWindow() {
 float rms=sqrtf(energy/3840.0f); energy=0; ++windows;
 uint32_t t=static_cast<uint32_t>((rawTimeSamples*1000ULL)/192000ULL); float relative=0;
 if(windows<=150) noise+=(rms-noise)/(float)windows;
 else {
   relative=rms/(noise+1.e-12f);
   bool legacyHot=relative>=1.8f;
   unsigned cfg=appliedPass.load();
   if(!active && cfg!=desiredPass.load()
#ifndef NZRT_HOST_TEST
       && !WildlifeML::passCaptureBusy()
#endif
   ){
     cfg=desiredPass.load();FirstPass::clear();appliedPass.store(cfg);
   }
   unsigned selected=cfg&3, shadow=cfg>>2;
#ifndef NZRT_HOST_TEST
   uint32_t started=esp_timer_get_time();
#endif
   bool hits[3]={legacyHot,false,false};
   if(selected==1 || shadow==2)hits[1]=FirstPass::evolved(pcmWindow);
   if(selected==2 || shadow==3)hits[2]=FirstPass::audible.load()->check(pcmWindow);
   bool hot=hits[selected],shadowHit=shadow && hits[shadow-1];
   ++passWindows;if(hot)++activeHot;if(shadowHit)++shadowHot;if(shadowHit&&!hot)++shadowOnly;
#ifndef NZRT_HOST_TEST
   unsigned dt=uint32_t(esp_timer_get_time()-started);lastPassUs.store(dt);
   if(dt>maxPassUs.load())maxPassUs.store(dt);
#endif
   if(hot) {
      if(!active) {
        active=true;eventPass=cfg;eventShadow=false;firstOn=t-20;eventPeak=relative;scorer.reset();
        eventStartUptime=clockOrigin+firstOn;
        WildlifeML::trigger(currentRun,events+1,clockOrigin+t);
        eventClip=WildlifeML::clipRequest();eventClipOwner=WildlifeML::clipOwnerSeq();eventBench=WildlifeML::benchActive();
      }
      lastOn=t;eventEndUptime=clockOrigin+t;
      if(relative>eventPeak)eventPeak=relative;
   }
   if(active){
     eventShadow|=shadowHit;
#ifndef NZRT_HOST_TEST
     uint32_t start=measureScore?esp_timer_get_time():0;
#endif
     scorer.window(pcmWindow,bandWindow,noise,hot);
#ifndef NZRT_HOST_TEST
     if(measureScore)scoreUs+=uint32_t(esp_timer_get_time())-start;
#endif
   }
   if(active && !hot && t-lastOn>=200) finishEvent(0);
   // Bounded bouts prevent continuous noise withholding the event forever.
   if(active && t-firstOn>=10000) finishEvent(3);
   if(!legacyHot&&relative<1.4f)noise+=0.003f*(rms-noise);
 }
 lastRms=rms;if(relative>maxRatio)maxRatio=relative;
 publish();
}
void processPcm(float pcm,bool keepHistory=true) {
     if(optionalHoldSamples) --optionalHoldSamples;
     else if(keepHistory) WildlifeML::pcm(pcm);
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
#ifndef NZRT_HOST_TEST
 WildlifeML::endTestStream();
#endif
 FirstPass::clear();
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
#ifndef NZRT_HOST_TEST
 WildlifeML::testGap(missingBlocks);
#endif
 WildlifeML::gap();
 FirstPass::clear();
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
static uint32_t decodeUs=0,analysisUs=0;
void blockTiming(uint32_t& decode,uint32_t& analysis,uint32_t& score){decode=decodeUs;analysis=analysisUs;score=scoreUs;}
void consume(const uint8_t* raw,size_t n,uint32_t captureEndUptimeMs) {
 if(captureEndUptimeMs) {
   // Reader-side timestamp, before queueing. Millisecond estimate with I2S
   // buffering latency, not sample-accurate hardware UTC.
   clockOrigin=captureEndUptimeMs-static_cast<uint32_t>(
      ((rawTimeSamples+n/2)*1000ULL)/192000ULL);
 }
 // Chronological little-endian 16-bit I2S words, each unpacked MSB first.
 // Integer CIC operations deliberately wrap modulo 32 bits.
#ifndef NZRT_HOST_TEST
 static unsigned previousStage=0;
 unsigned stage=WildlifeML::compareStage();
 measureScore=stage!=0;scoreUs=0;
 if(previousStage!=stage){
   const uint64_t runSamples=rawTimeSamples;
   reset(currentRun,clockOrigin);
   rawTimeSamples=runSamples; // retain the run-relative timeline across bench stages
   previousStage=stage;
 }
 size_t writable=0;
 int16_t* output=WildlifeML::testBlock(captureEndUptimeMs,n/2,writable);
#endif
 constexpr size_t chunk=128;
 float decoded[chunk];
 decodeUs=analysisUs=0;
 for(size_t first=0;first<n/2;first+=chunk){
   size_t count=n/2-first;if(count>chunk)count=chunk;
#ifndef NZRT_HOST_TEST
   uint32_t beginUs=stage?esp_timer_get_time():0;
#endif
   for(size_t j=0;j<count;++j){
     size_t i=(first+j)*2;
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
     for(unsigned tap=0;tap<8;++tap)pcm+=taps[tap]*(window[tap]+window[16-tap]);
     decoded[j]=pcm;
   }
#ifndef NZRT_HOST_TEST
   uint32_t decodedAt=stage?esp_timer_get_time():0;
   decodeUs+=decodedAt-beginUs;
#endif
   for(size_t j=0;j<count;++j){
     float pcm=decoded[j];
#ifdef NZRT_HOST_TEST
     processPcm(pcm);
#else
     size_t sampleIndex=first+j;
     if(sampleIndex<writable)output[sampleIndex]=int16_t(lrintf(std::max(-1.f,std::min(32767.f/32768.f,pcm))*32768.f));
     if(stage==1){++rawTimeSamples;continue;}
     processPcm(pcm,stage==0);
#endif
   }
#ifndef NZRT_HOST_TEST
   if(stage)analysisUs+=uint32_t(esp_timer_get_time())-decodedAt;
#endif
 }
#ifndef NZRT_HOST_TEST
 if(writable)WildlifeML::finishTestBlock(writable);
#endif
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
