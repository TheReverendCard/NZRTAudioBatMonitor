#include "WildlifeJournal.h"
#include <cassert>
#include <iostream>
SerialT Serial;Store store;FS SPIFFS;uint64_t fakeUs=0;
int main(){using namespace WildlifeJournal;
 // All monitoring writes are RAM-only, including boot and health.
 for(int i=0;i<20;++i){Writer w;assert(w);w.print("healthy\n");assert(w.close());}
 assert(store.ops==0);service();assert(store.ops==0);assert(spool().committed==20);
 {FlashWriter w;assert(!w);}assert(store.ops==0);
 {Reader r;assert(!r.good());}assert(store.ops==0);assert(!erase());assert(store.ops==0);
 uint8_t* data;uint64_t token;size_t n=prepareUpload(data,token);assert(n==20*8);
 finishUpload(false,token);assert(hasPendingUpload());
 n=prepareUpload(data,token);finishUpload(true,token);assert(!hasPendingUpload());
 assert(!spool().empty()); // ACK does not silently destroy the local RAM copy.
 // Simulate Arduino 2.0.17 garbage size for a newly CREATED append handle.
 store.newAppendSize=1647208303UL;RtWatch::sig().flashIdle=true;
 service();assert(stats().verified==1);assert(stats().verifyOffset==0);
 assert(store.appendSizeCalls==0);assert(stats().errors==0);assert(spool().flashSaved==1);
 // Oversized existing file is rejected before any seek/write/repair.
 store.fakeReadSize=1647208303UL;size_t writes=store.writes,renames=store.renames;
 service();assert(stats().latched);assert(stats().errors==1);assert(std::string(stats().lastReason)=="invalid_size");assert(store.writes==writes);assert(store.renames==renames);
 size_t ops=store.ops;fakeUs+=1800000000ULL;service();assert(store.ops==ops); // No timed retry after 30 minutes.
 {Writer w;w.print("after flash fault\n");assert(w.close());}assert(store.ops==ops);
 n=prepareUpload(data,token);assert(n);finishUpload(true,token); // WiFi path survives flash failure.
 // Independent clean state: a short/corrupt write does not remove queued data.
 stats()=Stats();store.fakeReadSize=0;store.corrupt=true;auto saved=spool().flashSaved;
 service();assert(stats().latched);assert(spool().flashSaved==saved);
 assert(stats().repairPending);ops=store.ops;fakeUs+=901000000ULL;service();assert(store.ops==ops);
 char b[512];ramStatus(b,sizeof(b));assert(strstr(b,"latched=1"));assert(strstr(b,"volatile=1"));
 assert(strlen(b)<sizeof(b)-1);
 std::cout<<"GUARD4_JOURNAL_PASS protected_flash_ops=0 new_file_size_bug=covered oversized_file=blocked timed_repair=disabled fault_queue_retained=1 wifi_after_fault=1\n";
}
