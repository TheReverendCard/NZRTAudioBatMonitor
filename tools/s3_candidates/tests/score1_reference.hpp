#pragma once
#include <cmath>
#include <stdint.h>
#include <stddef.h>

// Portable experimental ranking, not a probability or species classifier.
// No allocation, no flash access. Called only by the low-priority DSP worker.
namespace WildlifeScoring {
constexpr const char* VERSION = "RT-SCORE-1";
constexpr size_t FRAME = 256;
constexpr size_t WINDOW = 3840;
constexpr float FRAME_MS = 1000.0f * FRAME / 192000.0f;
struct Features {
  uint32_t pulses=0, short_pulses=0, good_gaps=0;
  uint32_t voiced_frames=0, narrow_frames=0, harmonic_frames=0;
  float pulse_mean_ms=0, pulse_max_ms=0, gap_mean_ms=0;
  float freq_mean_khz=0, freq_min_khz=0, freq_max_khz=0;
  float duty=0, harmonic_fraction=0;
  uint8_t score=0;
  bool bat_like=false;
};

class Analyzer {
  // Scratch and lookup tables live in the static Analyzer, not the task stack.
  float re[FRAME], im[FRAME], hann[FRAME], cs[FRAME/2], sn[FRAME/2];
  float power[FRAME/2+1];
  Features f;
  uint32_t frame=0, firstVoice=0, lastVoice=0, pulseFrames=0;
  uint32_t lastPulseEnd=0, gapCount=0;
  float pulseSum=0, gapSum=0, freqSum=0;

  void endPulse() {
    if(!pulseFrames) return;
    float ms=pulseFrames*FRAME_MS;
    ++f.pulses;
    if(ms>=FRAME_MS && ms<=20.0f) ++f.short_pulses;
    pulseSum+=ms;
    if(ms>f.pulse_max_ms) f.pulse_max_ms=ms;
    lastPulseEnd=lastVoice+1;
    pulseFrames=0;
  }
  float around(int bin) const {
    float result=0;
    for(int k=bin-1;k<=bin+1;++k)
      if(k>=1 && k<(int)FRAME/2) result+=power[k];
    return result;
  }
  bool lowerPeak(int bin, float upper) const {
    if(bin<5 || bin>int(FRAME/2)-5) return false;
    float local=0;
    for(int k=2;k<=4;++k) local+=power[bin-k]+power[bin+k];
    // Exact same 1.333ms frame, expected f/2 or f/3 +/- one FFT bin.
    // Require a lower peak above local background and relative to upper.
    float expected=around(bin);
    return expected>=0.15f*upper && expected>4.0f*(local/2.0f+1.e-20f);
  }
  void spectrum(const float* pcm) {
    float mean=0;
    for(size_t i=0;i<FRAME;++i) mean+=pcm[i];
    mean/=FRAME;
    for(size_t i=0;i<FRAME;++i) {re[i]=(pcm[i]-mean)*hann[i];im[i]=0;}
    for(size_t i=1,j=0;i<FRAME;++i) {
      size_t bit=FRAME>>1;
      for(;j&bit;bit>>=1) j^=bit;
      j^=bit;
      if(i<j) {float t=re[i];re[i]=re[j];re[j]=t;}
    }
    for(size_t length=2;length<=FRAME;length<<=1) {
      size_t half=length>>1, stride=FRAME/length;
      for(size_t base=0;base<FRAME;base+=length) {
        for(size_t k=0;k<half;++k) {
          size_t a=base+k,b=a+half,w=k*stride;
          float r=cs[w]*re[b]-sn[w]*im[b];
          float v=cs[w]*im[b]+sn[w]*re[b];
          re[b]=re[a]-r;im[b]=im[a]-v;
          re[a]+=r;im[a]+=v;
        }
      }
    }
    for(size_t i=0;i<=FRAME/2;++i) power[i]=re[i]*re[i]+im[i]*im[i];
    int peak=24; float total=0;
    // 750Hz/bin, 18..45kHz. Peak location is approximate, not a call contour.
    for(int k=24;k<=60;++k) {total+=power[k];if(power[k]>power[peak])peak=k;}
    float upper=around(peak);
    if(total<=1.e-20f || upper<0.25f*total) return;
    ++f.narrow_frames;
    float khz=peak*0.75f;
    freqSum+=khz;
    if(!f.freq_min_khz || khz<f.freq_min_khz) f.freq_min_khz=khz;
    if(khz>f.freq_max_khz) f.freq_max_khz=khz;
    // A fundamental can itself be above 18kHz and stronger than its upper
    // harmonic. Check other prominent local upper peaks in this same frame.
    for(int k=24;k<=60;++k) {
      if(power[k]<power[k-1] || power[k]<power[k+1]) continue;
      float candidate=around(k);
      if(candidate<0.5f*upper) continue;
      if(lowerPeak((k+1)/2,candidate) || lowerPeak((k+1)/3,candidate)) {
        ++f.harmonic_frames;break;
      }
    }
  }
public:
  Analyzer() {
    constexpr float piValue=3.14159265358979323846f;
    for(size_t i=0;i<FRAME;++i) hann[i]=0.5f-0.5f*cosf(2*piValue*i/(FRAME-1));
    for(size_t i=0;i<FRAME/2;++i) {cs[i]=cosf(2*piValue*i/FRAME);sn[i]=-sinf(2*piValue*i/FRAME);}
    reset();
  }
  void reset() {
    f=Features{};
    frame=firstVoice=lastVoice=pulseFrames=lastPulseEnd=gapCount=0;
    pulseSum=gapSum=freqSum=0;
  }
  void window(const float* pcm,const float* band,float noise,bool hot) {
    for(size_t offset=0;offset<WINDOW;offset+=FRAME,++frame) {
      float energy=0;
      if(hot) for(size_t i=offset;i<offset+FRAME;++i) energy+=band[i]*band[i];
      bool voice=hot && energy/FRAME>=noise*noise*1.8f*1.8f;
      if(!voice) {endPulse();continue;}
      if(!f.voiced_frames) firstVoice=frame;
      if(!pulseFrames && f.pulses) {
        float gap=(frame-lastPulseEnd)*FRAME_MS;
        ++gapCount;gapSum+=gap;
        if(gap>=15.0f && gap<=300.0f) ++f.good_gaps;
      }
      ++f.voiced_frames;++pulseFrames;lastVoice=frame;
      spectrum(pcm+offset);
    }
  }
  Features finish(float peak) {
    endPulse();
    f.pulse_mean_ms=f.pulses?pulseSum/f.pulses:0;
    f.gap_mean_ms=gapCount?gapSum/gapCount:0;
    f.freq_mean_khz=f.narrow_frames?freqSum/f.narrow_frames:0;
    f.duty=f.voiced_frames?float(f.voiced_frames)/(lastVoice-firstVoice+1):0;
    f.harmonic_fraction=f.narrow_frames?float(f.harmonic_frames)/f.narrow_frames:0;
    // Initial explicit weights. No deployment-site learning or auto tuning yet.
    int score=peak>=3.0f?20:(peak>=2.2f?15:8);
    if(f.pulses>=3) score+=20; else if(f.pulses==2) score+=12;
    if(f.pulses && f.short_pulses*2>=f.pulses) score+=25;
    if(f.voiced_frames && f.narrow_frames*2>=f.voiced_frames) score+=25;
    if(f.good_gaps) score+=10;
    if(f.harmonic_fraction>=0.5f) score-=5; // supporting evidence only
    if(f.pulse_max_ms>100.0f) score-=20;
    if(score<0) score=0;
    if(score>100) score=100;
    f.score=(uint8_t)score;
    f.bat_like=score>=65 && f.pulses>=2 && f.short_pulses>0 &&
      f.voiced_frames>0 && f.narrow_frames*2>=f.voiced_frames;
    return f;
  }
};
} // namespace WildlifeScoring
