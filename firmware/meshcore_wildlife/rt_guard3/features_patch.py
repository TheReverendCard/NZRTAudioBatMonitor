def upgrade(s):
 s=s.replace('#include <algorithm>','#include <algorithm>\n#include "RTFeatureControl.h"')
 # Make the FFT cooperatively cancellable, retaining all original arithmetic.
 s=s.replace('inline void fft(float* re,float* im) {','inline bool fft(float* re,float* im,bool(*check)(void*),void* ctx) {')
 s=s.replace('for(size_t len=2;len<=N;len*=2){double','for(size_t len=2;len<=N;len*=2){if(check&&!check(ctx))return false;double')
 s=s.replace('for(size_t i=0;i<N;i+=len){float','for(size_t i=0;i<N;i+=len){if((i%256)==0&&check&&!check(ctx))return false;float')
 s=s.replace('for(size_t j=0;j<len/2;++j){size_t','for(size_t j=0;j<len/2;++j){if((j%256)==0&&check&&!check(ctx))return false;size_t')
 s=s.replace('wr=nr;}}}\n}', 'wr=nr;}}}\n return true;\n}')
 s=s.replace('void (*yieldFn)()=nullptr) {','void (*yieldFn)()=nullptr,bool(*check)(void*)=nullptr,void* ctx=nullptr) {')
 s=s.replace('ptrdiff_t center=','if((j%128)==0&&check&&!check(ctx))return false;\n   ptrdiff_t center=')
 s=s.replace('  fft(re,im);','  if(!fft(re,im,check,ctx))return false;')
 s=s.replace('float base=quantile(row,frames,.5);','float base;if(!RTFeatureControl::quantile(row,frames,.5,base,check,ctx))return false;')
 s=s.replace('out[band*5+1]=quantile(strength,frames,.9);out[band*5+2]=quantile(strength,frames,.99);','if(!RTFeatureControl::quantile(strength,frames,.9,out[band*5+1],check,ctx))return false;\n  if(!RTFeatureControl::quantile(strength,frames,.99,out[band*5+2],check,ctx))return false;')
 s=s.replace('out[162]=quantile(spec,BINS*frames,.99);','if(!RTFeatureControl::quantile(spec,BINS*frames,.99,out[162],check,ctx))return false;')
 return s
