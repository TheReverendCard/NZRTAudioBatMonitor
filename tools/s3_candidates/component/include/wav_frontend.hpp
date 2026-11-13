#pragma once
// Bounded 2-second 192kHz mono PCM16 extractor for WAV feature schema 1.
// Training feature source: 27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923
// No allocation inside compute. Caller owns ~610 KB workspace (PSRAM on S3).
#include "s3_math.hpp"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstddef>
namespace bat_s3_wav {
constexpr size_t N=1024, HOP=512, BINS=395, MAX_SAMPLES=384000;
constexpr size_t MAX_FRAMES=1+(MAX_SAMPLES/2-N)/HOP;
constexpr size_t WORK_FLOATS=BINS*MAX_FRAMES+MAX_FRAMES*2+N*3+3;
static const float halfband[41]={
0,-.0010514587726751215f,0,.0025089668121477146f,0,-.0048948343392875718f,0,.0085565590024814057f,0,-.013989973238435149f,
0,.022023120574074614f,0,-.034340179881744919f,0,.055288283911857021f,0,-.10093019739773386f,0,.31670034568030075f,
.50025873529803011f,.31670034568030075f,0,-.10093019739773386f,0,.055288283911857021f,0,-.034340179881744919f,0,.022023120574074614f,
0,-.013989973238435149f,0,.0085565590024814057f,0,-.0048948343392875718f,0,.0025089668121477146f,0,-.0010514587726751215f,0};
inline float quantile(float* v,size_t n,double p) {
 const double at=(n-1)*p;size_t lo=(size_t)at;std::nth_element(v,v+lo,v+n);
 float a=v[lo];if(lo+1==n)return a;
 float b=*std::min_element(v+lo+1,v+n);return float(a+(b-a)*(at-lo));
}
inline bool compute(const int16_t* audio,size_t n,float* work,float out[165],void (*yieldFn)()=nullptr) {
 if(!audio||!work||!out||n<4096||n>MAX_SAMPLES)return false;
 const size_t frames=1+((n+1)/2-N)/HOP;
 float *spec=work,*row=spec+BINS*MAX_FRAMES,*strength=row+MAX_FRAMES;
 float *buf=reinterpret_cast<float*>((reinterpret_cast<uintptr_t>(strength+MAX_FRAMES)+15u)&~uintptr_t(15u)),*hann=buf+2*N;
 // Call bat_s3::fft_init() during setup, before capture, for shared 2048-entry tables.
 for(size_t j=0;j<N;++j)hann[j]=float(.5-.5*cos(6.283185307179586*j/N));
 for(size_t t=0;t<frames;++t){double mean=0;
  for(size_t j=0;j<N;++j){double acc=0;ptrdiff_t center=2*(t*HOP+j);
   for(int d=-20;d<=20;++d){ptrdiff_t a=center+d;if(a>=0&&size_t(a)<n)acc+=(double(audio[a])/32768.)*halfband[20-d];}
   buf[2*j]=float(acc);mean+=buf[2*j];}
  mean/=N;for(size_t j=0;j<N;++j){buf[2*j]=float((buf[2*j]-mean)*hann[j]);buf[2*j+1]=0;}
  if(!bat_s3::fft(buf,N))return false;
  for(size_t f=0;f<BINS;++f){size_t k=f+86;float mag=sqrtf(buf[2*k]*buf[2*k]+buf[2*k+1]*buf[2*k+1])/512.f;spec[f*frames+t]=log10f(std::max(mag,1.e-8f));}
  if(yieldFn)yieldFn();
 }
 double sum=0,ss=0;float mx=0;
 for(size_t f=0;f<BINS;++f){float* p=spec+f*frames;std::copy(p,p+frames,row);float base=quantile(row,frames,.5);
  for(size_t t=0;t<frames;++t){p[t]=std::max(0.f,std::min(3.f,(p[t]-base)*2.f))/3.f;sum+=p[t];ss+=double(p[t])*p[t];mx=std::max(mx,p[t]);}}
 size_t bin=0;
 for(int band=0;band<32;++band){std::fill(strength,strength+frames,0.f);size_t size=BINS/32+(band<int(BINS%32)?1:0);
  for(size_t f=bin;f<bin+size;++f){float* p=spec+f*frames;std::copy(p,p+frames,row);float base=quantile(row,frames,.5);
   for(size_t t=0;t<frames;++t)strength[t]=std::max(strength[t],std::max(0.f,p[t]-base));}
  double avg=0;size_t count=0;float maximum=0;for(size_t t=0;t<frames;++t){avg+=strength[t];count+=strength[t]>.25f;maximum=std::max(maximum,strength[t]);}
  out[band*5]=float(avg/frames);out[band*5+1]=quantile(strength,frames,.9);out[band*5+2]=quantile(strength,frames,.99);
  out[band*5+3]=maximum;out[band*5+4]=float(double(count)/frames);bin+=size;if(yieldFn)yieldFn();
 }
 double mean=sum/(BINS*frames);out[160]=float(mean);out[161]=float(sqrt(std::max(0.,ss/(BINS*frames)-mean*mean)));
 out[162]=quantile(spec,BINS*frames,.99);out[163]=mx;out[164]=float(log1p(double(frames)));
 for(int i=0;i<165;++i){if(!std::isfinite(out[i]))return false;}
 return true;
}
}
