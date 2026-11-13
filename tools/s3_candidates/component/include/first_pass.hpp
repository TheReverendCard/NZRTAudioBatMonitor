// Candidate kernels. Caller owns aligned storage, serialises FFT initialisation,
// supplies continuous mono 192 kHz PCM and calls reset() at every input gap.
#pragma once
#include "s3_math.hpp"
namespace bat_s3 {
// Replaces only the RMS reduction in legacy; firmware retains filters, baseline,
// event lifecycle and trigger thresholds.
inline float legacy_rms(const float* aligned_band3840){
 return std::sqrt(dot(aligned_band3840,aligned_band3840,3840)/3840.f);
}
// Standalone legacy first-pass scorer starting at the post-decimation PCM boundary.
// Call prime() with the initial 9600 PCM samples, then check() per 3840 samples.
// When integrated after the original bandpass, use legacy_rms() alone.
struct alignas(16) Legacy {
 alignas(16) float band[3840];float h1=0,h2=0,l1=0,l2=0,noise=0;unsigned windows=0;
 void reset(){h1=h2=l1=l2=noise=0;windows=0;}
 float step(float x){
  float h=.65745519149f*x+h1;h1=-1.31491038298f*x+1.19391336772f*h+h2;h2=.65745519149f*x-.43590739824f*h;
  float l=.26471264609f*h+l1;l1=.52942529219f*h+.11506372344f*l+l2;l2=.26471264609f*h-.17391430782f*l;return l;
 }
 void prime(const float* x,int n){for(int i=0;i<n;i++)step(x[i]);}
 bool check(const float* x){for(int i=0;i<3840;i++)band[i]=step(x[i]);
  float rms=legacy_rms(band);if(++windows<=150){noise+=(rms-noise)/windows;return false;}
  float rel=rms/(noise+1.e-12f);bool hot=rel>=1.8f;if(!hot && rel<1.4f)noise+=.003f*(rms-noise);return hot;}
};
struct alignas(16) Audible {
 // Bluestein: convolution computes exactly the original 960 frequency bins.
 // Last chirp is a unit magnitude rotation; skip it for power-only output.
 alignas(16) float buf[4096], kernel[4096], winR[960],winI[960];
 float bg[2]={};unsigned warm=0;bool ready=false;
 void reset(){warm=0;bg[0]=bg[1]=0;}
 bool init(){ready=false;if(!fft_init())return false;reset();
  std::fill(kernel,kernel+4096,0.f);
  for(int i=0;i<960;++i){double a=3.141592653589793*((i*i)%1920)/960.;
   float c=std::cos(a),s=std::sin(a),w=.5-.5*std::cos(6.283185307179586*i/959.);
   winR[i]=c*w;winI[i]=-s*w;kernel[2*i]=c;kernel[2*i+1]=s;
   if(i){kernel[2*(2048-i)]=c;kernel[2*(2048-i)+1]=s;}}
  return ready=fft(kernel,2048);}
 bool energies(const float* x,float& a,float& u){
  if(!ready)return false;
  for(int i=0;i<960;i++){buf[2*i]=x[i]*winR[i];buf[2*i+1]=x[i]*winI[i];}
  std::fill(buf+1920,buf+4096,0.f);if(!fft(buf,2048))return false;
  for(int i=0;i<4096;i+=2){float r=buf[i],t=buf[i+1];buf[i]=r*kernel[i]-t*kernel[i+1];
   buf[i+1]=-(t*kernel[i]+r*kernel[i+1]);}
  if(!fft(buf,2048))return false;
  // Both original half-open bands start at even bins (aligned). Handle tails.
  a=(dot(buf+20,buf+20,128)+buf[148]*buf[148]+buf[149]*buf[149])/(65.f*2048*2048);
  u=(dot(buf+180,buf+180,268)+buf[448]*buf[448]+buf[449]*buf[449])/(135.f*2048*2048);
  return true;}
 bool check(const float*x,bool& hot){hot=false;for(int i=0;i<3840;i+=960){float a,u;
  if(!energies(x+i,a,u))return false;
  if(warm<10){++warm;bg[0]+=(a-bg[0])/warm;bg[1]+=(u-bg[1])/warm;continue;}
  float ar=(a+1.e-12f)/(bg[0]+1.e-12f),ur=(u+1.e-12f)/(bg[1]+1.e-12f);
  hot|=ur>=3.235937f && (ar<1.995262f || ur>=ar*3.981072f);
  bg[0]+=.024690088f*(a-bg[0]);bg[1]+=.024690088f*(u-bg[1]);}return true;}
};
// Diagnostic variants from offline audible.replay at 192 kHz.  The FFT buffer
// still holds transformed (unnormalised) bins after energies(); use it once.
enum class ReplayRule { Ultrasound, LowSide, Both };
template<ReplayRule rule> struct alignas(16) Replay : Audible {
 float lowbg[2]={};
 void reset(){Audible::reset();lowbg[0]=lowbg[1]=0;}
 bool init(){reset();return Audible::init();}
 bool check(const float* x,bool& hot){hot=false;
  for(int off=0;off<3840;off+=960){float a,u;if(!energies(x+off,a,u))return false;
   float low=0,mid=0,peak=-1;int bin=90;
   if(rule!=ReplayRule::Ultrasound){
    for(int i=90;i<225;i++){float e=buf[2*i]*buf[2*i]+buf[2*i+1]*buf[2*i+1];
     if(i<120)low+=e;if(i>=135 && i<165)mid+=e;
     if(e>peak){peak=e;bin=i;}}
    low/=30.f*2048*2048;mid/=30.f*2048*2048;
   }
   float rate=.024690088f;
   if(warm<10){++warm;rate=1.f/warm;}
   else {
    float ar=(a+1.e-12f)/(bg[0]+1.e-12f),ur=(u+1.e-12f)/(bg[1]+1.e-12f);
    bool audibleOK=ar<1.995262f || ur>=ar*3.981072f;
    bool lowTail=(bin>=115 && bin<=135 && std::max(0.f,low-lowbg[0])>2*std::max(0.f,mid-lowbg[1]));
    hot|=ur>=3.235937f && (rule!=ReplayRule::Both || audibleOK) && (rule==ReplayRule::Ultrasound || !lowTail);
   }
   bg[0]+=rate*(a-bg[0]);bg[1]+=rate*(u-bg[1]);
   lowbg[0]+=rate*(low-lowbg[0]);lowbg[1]+=rate*(mid-lowbg[1]);
  }return true;
 }
};
struct alignas(16) Evolved {
 alignas(16) float filtered[1920];float coef[5][3],z[5][2]{},bg[5]{};unsigned warm=0;
 Evolved(){const float band[][2]={{3000,12000},{18000,24000},{24000,27000},{27000,33000},{36000,44500}};
  for(int k=0;k<5;k++){float lo=band[k][0],hi=band[k][1],f=std::sqrt(lo*hi),w=6.28318530718f*f/192000.f,a=std::sin(w)*(hi-lo)/(2*f);
   coef[k][0]=a/(1+a);coef[k][1]=-2*std::cos(w)/(1+a);coef[k][2]=(1-a)/(1+a);}}
 void reset(){warm=0;for(auto& p:z)p[0]=p[1]=0;for(auto& b:bg)b=0;}
 bool check(const float*x,const float (&weights)[5][3],const float (&bias)[3],float threshold){
  bool hot=false;for(int start=0;start<3840;start+=1920){float h[]={bias[0],bias[1],bias[2]};
   for(int k=0;k<5;k++){if(!weights[k][0]&&!weights[k][1]&&!weights[k][2])continue;
    for(int i=0;i<1920;i++){float v=x[start+i]*coef[k][0],y=v+z[k][0];z[k][0]=z[k][1]-coef[k][1]*y;z[k][1]=-v-coef[k][2]*y;filtered[i]=y;}
    float en=dot(filtered,filtered,1920)/1920.f;
    if(warm<5){bg[k]+=(en-bg[k])/(warm+1);continue;}float v=std::min(8.f,en/(bg[k]+1.e-12f))-1;
    for(int j=0;j<3;j++)h[j]+=weights[k][j]*v;bg[k]+=.05f*(en-bg[k]);}
   if(warm<5){++warm;continue;}hot|=std::max(0.f,h[0])+std::max(0.f,h[1])-std::max(0.f,h[2])>threshold;}
  return hot;}
};
}
