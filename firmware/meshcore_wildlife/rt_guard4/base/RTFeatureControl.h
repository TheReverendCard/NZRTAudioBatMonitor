#pragma once
#include <algorithm>
#include <cstddef>
namespace RTFeatureControl {
// Interruptible selection.  Identical order-statistic interpolation to the
// reference extractor; check callbacks never change the numeric feature.
inline bool quantile(float* v,size_t n,double p,float& result,
                     bool (*check)(void*),void* context) {
  if (!n) return false;
  const double at=(n-1)*p;
  const ptrdiff_t k=ptrdiff_t(at);
  ptrdiff_t lo=0,hi=ptrdiff_t(n)-1;
  unsigned work=0;
  auto step=[&](){return (++work&255)!=0 || !check || check(context);};
  while(lo<hi) {
    if(check && !check(context))return false;
    const float pivot=v[lo+(hi-lo)/2];
    ptrdiff_t i=lo,j=hi;
    while(i<=j) {
      while(v[i]<pivot){++i;if(!step())return false;}
      while(v[j]>pivot){--j;if(!step())return false;}
      if(i<=j){std::swap(v[i++],v[j--]);if(!step())return false;}
    }
    if(k<=j)hi=j;
    else if(k>=i)lo=i;
    else break;
  }
  const float a=v[k];
  if(size_t(k)+1==n){result=a;return true;}
  float b=v[k+1];
  for(size_t i=size_t(k)+2;i<n;++i){b=std::min(b,v[i]);if(!step())return false;}
  result=float(a+(b-a)*(at-k));
  return !check || check(context);
}
}
