#pragma once
// Bounded 2-second 192kHz mono PCM16 extractor for WAV feature schema 1.
// Training feature source: 27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923
// GUARD-4: exact Q33 FIR, optional internal-RAM FFT/window scratch.
// Every float coefficient is an exact multiple of 2^-33.  PCM16 dot sums
// fit within 50 signed bits, so this equals the reference double sum before
// its float rounding.  No changed filter, float-FIR approximation or fast-math.
// No allocation inside compute. Caller owns ~610 KB workspace (PSRAM on S3).
#include <algorithm>
#include "RTFeatureControl.h"
#include <cmath>
#include <cstdint>
#include <cstddef>
namespace RTFeatures {
struct Profile {uint32_t decimate=0,window=0,fft=0,spectrum=0,normalize=0,bands=0,quantile=0;};
constexpr size_t N=1024, HOP=512, BINS=395, MAX_SAMPLES=384000;
constexpr size_t MAX_FRAMES=1+(MAX_SAMPLES/2-N)/HOP;
constexpr size_t HOT_FLOATS=N*5+HOP;
constexpr size_t WORK_FLOATS=BINS*MAX_FRAMES+MAX_FRAMES*2+N*5+HOP;
static const float halfband[41]={
0,-.0010514587726751215f,0,.0025089668121477146f,0,-.0048948343392875718f,0,.0085565590024814057f,0,-.013989973238435149f,
0,.022023120574074614f,0,-.034340179881744919f,0,.055288283911857021f,0,-.10093019739773386f,0,.31670034568030075f,
.50025873529803011f,.31670034568030075f,0,-.10093019739773386f,0,.055288283911857021f,0,-.034340179881744919f,0,.022023120574074614f,
0,-.013989973238435149f,0,.0085565590024814057f,0,-.0048948343392875718f,0,.0025089668121477146f,0,-.0010514587726751215f,0};
static const int64_t halfbandQ33[41]={0LL,-9031962LL,0LL,21551860LL,0LL,-42046308LL,0LL,73500280LL,0LL,-120172952LL,0LL,189177168LL,0LL,-294979904LL,0LL,474922752LL,0LL,-866983808LL,0LL,2720435200LL,4297189888LL,2720435200LL,0LL,-866983808LL,0LL,474922752LL,0LL,-294979904LL,0LL,189177168LL,0LL,-120172952LL,0LL,73500280LL,0LL,-42046308LL,0LL,21551860LL,0LL,-9031962LL,0LL};
inline float decimate(const int16_t* audio,size_t n,ptrdiff_t center){
   // Symmetric integer FIR: pairing cannot change the exact bounded sum.
   int64_t acc=int64_t(audio[center])*halfbandQ33[20];
   if(center>=19 && size_t(center)+19<n){
    for(int d=1;d<=19;d+=2)
     acc+=int64_t(int32_t(audio[center-d])+audio[center+d])*halfbandQ33[20-d];
   }else for(int d=1;d<=19;d+=2){
    int32_t pair=0;
    if(center>=d)pair+=audio[center-d];
    if(size_t(center)+d<n)pair+=audio[center+d];
    acc+=int64_t(pair)*halfbandQ33[20-d];
   }
   return float(acc)*(1.0f/281474976710656.0f);
}
inline float quantile(float* v,size_t n,double p) {
 const double at=(n-1)*p;size_t lo=(size_t)at;std::nth_element(v,v+lo,v+n);
 float a=v[lo];if(lo+1==n)return a;
 float b=*std::min_element(v+lo+1,v+n);return float(a+(b-a)*(at-lo));
}
inline void twiddles(float* real,float* imag) {
 for(size_t len=2;len<=N;len*=2){
  double ang=-6.283185307179586/len;float br=cos(ang),bi=sin(ang),wr=1,wi=0;
  for(size_t j=0;j<len/2;++j){size_t k=len/2-1+j;real[k]=wr;imag[k]=wi;
   float nr=wr*br-wi*bi;wi=wr*bi+wi*br;wr=nr;}
 }
}
inline bool fft(float* re,float* im,bool(*check)(void*),void* ctx,const float* real,const float* imag) {
 for(size_t i=1,j=0;i<N;++i){size_t bit=N/2;for(;j&bit;bit>>=1)j^=bit;j^=bit;if(i<j){std::swap(re[i],re[j]);std::swap(im[i],im[j]);}}
 unsigned operations=0;
 for(size_t len=2;len<=N;len*=2){if(check&&!check(ctx))return false;
  for(size_t i=0;i<N;i+=len){for(size_t j=0;j<len/2;++j){if((operations++%128)==0&&check&&!check(ctx))return false;size_t a=i+j,b=a+len/2;
   float wr=real[len/2-1+j],wi=imag[len/2-1+j];
   float qr=re[b]*wr-im[b]*wi,qi=re[b]*wi+im[b]*wr;
   re[b]=re[a]-qr;im[b]=im[a]-qi;re[a]+=qr;im[a]+=qi;}}}
 return true;
}
inline bool compute(const int16_t* audio,size_t n,float* work,float out[165],void (*yieldFn)()=nullptr,bool(*check)(void*)=nullptr,void* ctx=nullptr,float* hot=nullptr,Profile* profile=nullptr,uint32_t(*clockUs)()=nullptr) {
 if(!audio||!work||!out||n<4096||n>MAX_SAMPLES)return false;
 const size_t frames=1+((n+1)/2-N)/HOP;
 float *spec=work,*row=spec+BINS*MAX_FRAMES,*strength=row+MAX_FRAMES,*re=hot?hot:strength+MAX_FRAMES,*im=re+N,*hann=im+N;
 for(size_t j=0;j<N;++j)hann[j]=float(.5-.5*cos(6.283185307179586*j/N));
 float* overlap=hann+N;
 float* twiddleRe=overlap+HOP;float* twiddleIm=twiddleRe+N;
 twiddles(twiddleRe,twiddleIm);
 Profile unused;Profile& times=profile?*profile:unused;uint32_t checkpoint=clockUs?clockUs():0;
 auto mark=[&](uint32_t& value){if(clockUs){uint32_t now=clockUs();value+=now-checkpoint;checkpoint=now;}};
 for(size_t t=0;t<frames;++t){double mean=0;
  if(t)std::copy(overlap,overlap+HOP,re);
  for(size_t j=t?HOP:0;j<N;++j){
   if((j%128)==0&&check&&!check(ctx))return false;
   re[j]=decimate(audio,n,2*(t*HOP+j));
  }
  std::copy(re+HOP,re+N,overlap);
  mark(times.decimate);
  for(size_t j=0;j<N;++j)mean+=re[j];
  mean/=N;for(size_t j=0;j<N;++j){re[j]=float((re[j]-mean)*hann[j]);im[j]=0;}
  mark(times.window);
  if(!fft(re,im,check,ctx,twiddleRe,twiddleIm))return false;
  mark(times.fft);
  for(size_t f=0;f<BINS;++f){size_t k=f+86;float mag=sqrtf(re[k]*re[k]+im[k]*im[k])/512.f;spec[f*frames+t]=log10f(std::max(mag,1.e-8f));}
  if(yieldFn)yieldFn();
  mark(times.spectrum);
 }
 double sum=0,ss=0;float mx=0;
 for(size_t f=0;f<BINS;++f){float* p=spec+f*frames;std::copy(p,p+frames,row);float base;if(!RTFeatureControl::quantile(row,frames,.5,base,check,ctx))return false;
  for(size_t t=0;t<frames;++t){p[t]=std::max(0.f,std::min(3.f,(p[t]-base)*2.f))/3.f;sum+=p[t];ss+=double(p[t])*p[t];mx=std::max(mx,p[t]);}}
 mark(times.normalize);
 size_t bin=0;
 for(int band=0;band<32;++band){std::fill(strength,strength+frames,0.f);size_t size=BINS/32+(band<int(BINS%32)?1:0);
  for(size_t f=bin;f<bin+size;++f){float* p=spec+f*frames;std::copy(p,p+frames,row);float base;if(!RTFeatureControl::quantile(row,frames,.5,base,check,ctx))return false;
   for(size_t t=0;t<frames;++t)strength[t]=std::max(strength[t],std::max(0.f,p[t]-base));}
  double avg=0;size_t count=0;float maximum=0;for(size_t t=0;t<frames;++t){avg+=strength[t];count+=strength[t]>.25f;maximum=std::max(maximum,strength[t]);}
  out[band*5]=float(avg/frames);if(!RTFeatureControl::quantile(strength,frames,.9,out[band*5+1],check,ctx))return false;
  if(!RTFeatureControl::quantile(strength,frames,.99,out[band*5+2],check,ctx))return false;
  out[band*5+3]=maximum;out[band*5+4]=float(double(count)/frames);bin+=size;if(yieldFn)yieldFn();
 }
 mark(times.bands);
 double mean=sum/(BINS*frames);out[160]=float(mean);out[161]=float(sqrt(std::max(0.,ss/(BINS*frames)-mean*mean)));
 if(!RTFeatureControl::quantile(spec,BINS*frames,.99,out[162],check,ctx))return false;out[163]=mx;out[164]=float(log1p(double(frames)));
 mark(times.quantile);
 for(int i=0;i<165;++i)if(!std::isfinite(out[i]))return false;return true;
}
}
