#include "RTFeatureControl.h"
#include "RTFeatures.h"
#include "RTLogSpool.h"
#include "RTClipLease.h"
#include "RTJournalPolicy.h"
#include "RTFeaturesReference.h"
#include <cassert>
#include <cstdio>
#include <cstring>
static float a[4096],b[4096];
static unsigned calls=0;
bool cancel(void*){return ++calls<3;}
static int16_t pcm[4096];
float reference(const int16_t* audio,size_t n,ptrdiff_t center){
 double acc=0;for(int d=-19;d<=19;d+=2){ptrdiff_t a=center+d;
 if(d==1)acc+=(double(audio[center])/32768.)*RTFeatures::halfband[20];
 if(a>=0&&size_t(a)<n)acc+=(double(audio[a])/32768.)*RTFeatures::halfband[20-d];}
 return float(acc);
}
extern "C" void app_main(){
 uint32_t seed=51;unsigned fir=0;
 for(unsigned kind=0;kind<12;++kind){
  for(unsigned i=0;i<4096;++i){seed=seed*1664525+1013904223;pcm[i]=kind==0?0:kind==1?32767:kind==2?-32768:int16_t(seed>>16);}
  for(unsigned i=0;i<4096;i+=2){float a=reference(pcm,4096,i),b=RTFeatures::decimate(pcm,4096,i);assert(a==b);++fir;}
 }
 uint8_t mem[128],out[128];RTLogSpool::Queue queue;assert(queue.init(mem,sizeof(mem)));uint64_t tok;
 for(unsigned i=0;i<1000;++i){assert(queue.push((const uint8_t*)"sample\n",7));assert(queue.upload(out,sizeof(out),tok)==7);assert(queue.confirm(tok));}
 assert(queue.unconfirmedLost==0);
 uint32_t r=17;unsigned checked=0;
 for(unsigned n:{2u,17u,373u,4096u})for(double q:{.5,.9,.99}){
  for(unsigned i=0;i<n;++i){r=r*1664525+1013904223;a[i]=float(int(r>>16)-32768)/32768;}
  memcpy(b,a,n*sizeof(float));float expected=RTFeaturesReference::quantile(a,n,q),got=0;
  assert(RTFeatureControl::quantile(b,n,q,got,nullptr,nullptr));assert(got==expected);++checked;
 }
 calls=0;float v=0;assert(!RTFeatureControl::quantile(b,4096,.99,v,cancel,nullptr));
 RTClipLease l;l.publish(true,true);assert(l.claim());l.delivery=false;assert(!l.releasable());l.score=RTClipLease::Done;assert(!l.releasable());l.score=RTClipLease::Reported;assert(l.releasable());
 RTJournalPolicy p;uint32_t t=0xffffff00u;p.failure(t);p.failure(t+31000);p.failure(t+62000);assert(p.blocked(t+63000));assert(!p.blocked(t+962000));
 printf("GUARD4_S3_PASS fir=%u quantiles=%u cancellation=1 lease=1 spool_wraps=1000\n",fir,checked);fflush(stdout);
}
