#pragma once
#include <cmath>
#include <cstring>
#include <cstdint>
#include "wav_mlp_model_parameters.h"
namespace RTModel {
constexpr size_t COUNT=6187, BYTES=24+COUNT*4;
struct Model {float threshold;float values[COUNT];};
inline void builtin(Model& m) {
 using namespace nzrt::wav_mlp;m.threshold=kValidationThreshold;float* p=m.values;
 #define COPY_ARRAY(a) memcpy(p,a,sizeof(a));p+=sizeof(a)/sizeof(float)
 COPY_ARRAY(kScalerMean);COPY_ARRAY(kScalerScale);COPY_ARRAY(kWeights0);COPY_ARRAY(kBias0);
 COPY_ARRAY(kWeights1);COPY_ARRAY(kBias1);COPY_ARRAY(kWeights2);COPY_ARRAY(kBias2);
 #undef COPY_ARRAY
}
inline bool valid(const Model& m) {
 if(!std::isfinite(m.threshold)||m.threshold<=0||m.threshold>=1)return false;
 for(size_t i=0;i<COUNT;++i)if(!std::isfinite(m.values[i]))return false;
 for(size_t i=165;i<330;++i)if(m.values[i]<1e-12f)return false;return true;
}
inline bool decode(const uint8_t* bytes,size_t n,Model& m) {
 if(n!=BYTES||memcmp(bytes,"NZRTMLP1",8))return false;
 uint32_t schema,count,feature;memcpy(&schema,bytes+8,4);memcpy(&count,bytes+12,4);memcpy(&feature,bytes+20,4);
 if(schema!=1||count!=COUNT||feature!=1)return false;
 memcpy(&m.threshold,bytes+16,4);memcpy(m.values,bytes+24,COUNT*4);return valid(m);
}
inline float score(const Model& m,const float f[165]) {
 const float *mean=m.values,*scale=mean+165,*w0=scale+165,*b0=w0+5280,*w1=b0+32,*b1=w1+512,*w2=b1+16,*b2=w2+16;
 double a[32],b[16];
 for(int j=0;j<32;++j){double z=b0[j];for(int i=0;i<165;++i){if(!std::isfinite(f[i]))return NAN;z+=(double(f[i])-mean[i])/scale[i]*w0[i*32+j];}a[j]=std::max(0.,z);}
 for(int j=0;j<16;++j){double z=b1[j];for(int i=0;i<32;++i)z+=a[i]*w1[i*16+j];b[j]=std::max(0.,z);}
 double z=b2[0];for(int i=0;i<16;++i)z+=b[i]*w2[i];return float(z>=0?1/(1+exp(-z)):exp(z)/(1+exp(z)));
}
}
