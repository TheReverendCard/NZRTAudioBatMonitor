#include "RTFeatures.h"
#include "RTFeaturesReference.h"
#include "RTClipLease.h"
#include "RTJournalPolicy.h"
#include <cassert>
#include <cstdio>
#include <vector>
#include <cstring>
int checks=0,stopAt=0;
bool stop(void*){return ++checks<stopAt;}
int main(){
 double bound=0;for(size_t i=0;i<41;++i){assert(double(RTFeatures::halfband[i])*8589934592.==double(RTFeatures::halfbandQ33[i]));bound+=fabs(double(RTFeatures::halfbandQ33[i]))*32768.;}assert(bound<1125899906842624.);

 std::vector<int16_t> x(RTFeatures::MAX_SAMPLES);
 std::vector<float> w(RTFeatures::WORK_FLOATS),v(w.size()),hot(RTFeatures::HOT_FLOATS);float a[165],b[165];
 uint32_t rng=42;unsigned compared=0;
 for(int kind=0;kind<30;++kind){
  for(size_t i=0;i<x.size();++i){rng=rng*1664525+1013904223;
   x[i]=kind==0?0:kind==1?300:kind==2?int16_t((rng>>16)-32768):
    kind==3?int16_t(12000*sin(6.283185307179586*41000*i/192000)):
    kind==4?int16_t((i%19200<1200)?22000*sin(6.283185307179586*(45000-10000.*(i%1200)/1200)*i/192000):int(rng%20)-10):
    kind==5?int16_t(i%2?32767:-32768):kind==6?int16_t(i==1024?32767:0):kind==7?int16_t(30000*sin(6.283185307179586*47000*i/192000)):kind==8?int16_t((i%9000<200)?15:0):int16_t((rng>>16)-32768);
  }
  size_t count=kind<6?x.size():size_t(4096+(kind*15539)%375904);
  assert(RTFeaturesReference::compute(x.data(),count,v.data(),a));
  assert(RTFeatures::compute(x.data(),count,w.data(),b,nullptr,nullptr,nullptr,hot.data()));
  for(int j=0;j<165;++j){assert(a[j]==b[j]);++compared;}
 }
 // Cancel at decimation, FFT, and late selection checkpoints; retry untouched PCM.
 for(int n:{1,200,10000}){checks=0;stopAt=n;assert(!RTFeatures::compute(x.data(),x.size(),w.data(),b,nullptr,stop,nullptr));assert(checks==n);}
 assert(RTFeatures::compute(x.data(),x.size(),w.data(),b));
 // Every ordering of reader completion retains the buffer until both are done.
 RTClipLease l;l.publish(true,true);assert(l.claim());assert(!l.claim());
 l.delivery=false;assert(!l.releasable());l.score=RTClipLease::Done;assert(!l.releasable());l.score=RTClipLease::Reported;assert(l.releasable());
 l.publish(true,true);assert(l.claim());l.score=RTClipLease::Reported;assert(!l.releasable());l.delivery=false;assert(l.releasable());
 RTJournalPolicy p;uint32_t t=0xffffff00u;p.failure(t);p.failure(t+30000);assert(!p.blocked(t+60000));p.failure(t+60000);assert(p.blocked(t+60001));assert(!p.blocked(t+60000+RTJournalPolicy::COOL));assert(p.trips==1);
 printf("GUARD4_FEATURE_PASS compared=%u cancellations=3 lease_orders=2 circuit_wrap=1\n",compared);
}
