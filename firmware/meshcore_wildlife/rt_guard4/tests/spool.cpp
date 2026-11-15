#include "RTLogSpool.h"
#include <cassert>
#include <cstring>
#include <cstdio>
int main(){uint8_t mem[64],out[64];RTLogSpool::Queue q;assert(q.init(mem,sizeof(mem)));
 auto push=[&](const char*s){return q.push((const uint8_t*)s,strlen(s));};
 assert(!push("incomplete"));assert(push("one\n"));assert(push("two\n"));uint64_t token=0;
 assert(q.upload(out,64,token)==8);assert(!memcmp(out,"one\ntwo\n",8));assert(q.confirm(token));
 assert(!q.pending());assert(q.oldest(out,64,token)==4);assert(q.saved(token));assert(q.flashSaved==1);
 for(int i=0;i<20;++i)assert(push("record\n"));assert(q.unconfirmedLost>0);assert(q.evicted>0);
 size_t n=q.upload(out,64,token);assert(n>0);assert(!q.confirm(token+1));assert(q.confirm(token));
 unsigned lost=q.unconfirmedLost;assert(push("next\n"));assert(q.unconfirmedLost==lost); // Evict oldest ACKed record.
 n=q.upload(out,64,token);assert(n==5&&!memcmp(out,"next\n",5));assert(q.confirm(token));
 // Thousands of wraps, bounded memory, exact data across wrap and ACK boundaries.
 q.clear();for(int i=0;i<10000;++i){assert(push("abcde\n"));assert(q.upload(out,64,token)==6);assert(!memcmp(out,"abcde\n",6));assert(q.confirm(token));assert(q.used()<=64);}
 printf("GUARD4_SPOOL_PASS wrap_cycles=10000 partial_rejected=1 lost_unacked_counted=1 ack_verified=1\n");
}
