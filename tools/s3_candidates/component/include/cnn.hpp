#pragma once
#include "s3_math.hpp"
namespace bat_s3 {
// One image window at a time. Input C,H,W; intermediate maps H,W,C.
// Caller provides scratch (prefer PSRAM), kept out of the audio capture task.
template<int CI,int CO,int K,bool first=false>
void conv(const float* in,int h,int w,const float* weights,const float* bias,float* out){
 constexpr int stride=(CI*K*K+3)&~3;
 alignas(16) float patch[stride]{};
 for(int y=0;y<(h+1)/2;y++)for(int x=0;x<(w+1)/2;x++){
  int n=0;
  for(int ky=0;ky<K;ky++)for(int kx=0;kx<K;kx++){
   int iy=2*y+ky-K/2,ix=2*x+kx-K/2;
   for(int c=0;c<CI;c++)patch[n++]=(iy<0||iy>=h||ix<0||ix>=w)?0:
      in[first?(c*h+iy)*w+ix:(iy*w+ix)*CI+c];}
  for(int o=0;o<CO;o++)*out++=std::max(0.f,bias[o]+dot(weights+o*stride,patch,stride));}
}
}
