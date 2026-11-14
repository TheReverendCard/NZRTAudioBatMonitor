#include "RTFeatureControl.h"
#include "RTClipLease.h"
#include "RTJournalPolicy.h"
#include "RTFeaturesReference.h"
#include <cassert>
#include <cstdio>
#include <cstring>
static float a[4096],b[4096];
static unsigned calls=0;
bool cancel(void*){return ++calls<3;}
extern "C" void app_main(){
 uint32_t r=17;unsigned checked=0;
 for(unsigned n:{2u,17u,373u,4096u})for(double q:{.5,.9,.99}){
  for(unsigned i=0;i<n;++i){r=r*1664525+1013904223;a[i]=float(int(r>>16)-32768)/32768;}
  memcpy(b,a,n*sizeof(float));float expected=RTFeaturesReference::quantile(a,n,q),got=0;
  assert(RTFeatureControl::quantile(b,n,q,got,nullptr,nullptr));assert(got==expected);++checked;
 }
 calls=0;float v=0;assert(!RTFeatureControl::quantile(b,4096,.99,v,cancel,nullptr));
 RTClipLease l;l.publish(true,true);assert(l.claim());l.delivery=false;assert(!l.releasable());l.score=RTClipLease::Done;assert(!l.releasable());l.score=RTClipLease::Reported;assert(l.releasable());
 RTJournalPolicy p;uint32_t t=0xffffff00u;p.failure(t);p.failure(t+31000);p.failure(t+62000);assert(p.blocked(t+63000));assert(!p.blocked(t+962000));
 printf("GUARD3_S3_PASS quantiles=%u cancellation=1 lease=1 circuit_wrap=1\n",checked);fflush(stdout);
}
