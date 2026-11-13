#pragma once
#include <cmath>
#include <cstddef>
#include <algorithm>
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#include "dsps_fft2r.h"
#include "dsps_dotprod.h"
#if !CONFIG_IDF_TARGET_ESP32S3 || !CONFIG_DSP_OPTIMIZED
#error "This candidate requires ESP32-S3 with CONFIG_DSP_OPTIMIZED=y"
#endif
#endif
namespace bat_s3 {
// Call only with 16-byte aligned inputs and n a multiple of four.
inline float dot(const float *a,const float *b,int n){
#ifdef ESP_PLATFORM
 float v; dsps_dotprod_f32_aes3(a,b,&v,n);return v;
#else
 float s=0;for(int i=0;i<n;i++)s+=a[i]*b[i];return s;
#endif
}
inline float prob(float x){ return 1.f/(1.f+std::exp(-x)); }
// Interleaved complex, forward unnormalised.  Shared ESP-DSP tables must be
// initialized once at startup for >=2048 points, never resized by other tasks.
inline bool fft_init(){
#ifdef ESP_PLATFORM
 return dsps_fft2r_init_fc32(nullptr,2048)==ESP_OK && dsps_fft_w_table_size>=2048;
#else
 return true;
#endif
}
inline bool fft(float *p,int n){
#ifdef ESP_PLATFORM
 return dsps_fft2r_fc32_aes3(p,n)==ESP_OK && dsps_bit_rev_fc32_ansi(p,n)==ESP_OK;
#else
 for(int i=1,j=0;i<n;i++){int k=n>>1;while(j&k){j^=k;k>>=1;}j^=k;
 if(i<j){std::swap(p[2*i],p[2*j]);std::swap(p[2*i+1],p[2*j+1]);}}
 for(int l=2;l<=n;l*=2)for(int k=0;k<l/2;k++){double a=-6.283185307179586*k/l;
 float c=std::cos(a),s=std::sin(a);for(int i=k;i<n;i+=l){int j=i+l/2;
 float r=p[2*j]*c-p[2*j+1]*s,t=p[2*j]*s+p[2*j+1]*c;
 p[2*j]=p[2*i]-r;p[2*j+1]=p[2*i+1]-t;p[2*i]+=r;p[2*i+1]+=t;}}
 return true;
#endif
}
}
