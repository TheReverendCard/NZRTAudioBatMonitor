#include "WildlifeUpload.h"
#include <cassert>
#include <iostream>
SerialT Serial;Store store;FS SPIFFS;uint64_t fakeUs=30000000;
bool events=true,mlWanted=true;unsigned mlCalls=0,mlFailures=0;
namespace WildlifeMic {
bool hasLiveEvents(){return events;}size_t formatLiveBatch(char*b,size_t n){snprintf(b,n,"NZRT FIELD test=1\n");return 1;}void ackLiveBatch(size_t){}
}
namespace WildlifeML {
bool wantsNetwork(){return mlWanted;}bool testUploadDue(){return false;}void connected(){++mlCalls;}void networkFailed(){++mlFailures;}
}
int main(){using namespace WildlifeJournal;
 {Writer w;w.println("NZRT ML session=abcd test=1");assert(w.close());}
 httpWrongHash()=true;assert(!WildlifeUpload::sendRam(1794692281));assert(hasPendingUpload());assert(!ram().busy);
 httpWrongHash()=false;assert(WildlifeUpload::sendRam(1794692281));assert(!hasPendingUpload());assert(!spool().empty());assert(store.ops==0);
 // Under continuous report load, an ML/network-control turn is reserved after two reports.
 for(int i=0;i<3;++i){
  {Writer w;w.println("NZRT FIELD test=1");w.close();}
  fakeUs+=6000000;WildlifeUpload::connecting=false;
  assert(WildlifeUpload::tick("test","test",1794692281));
  if(i==2)assert(WildlifeUpload::purpose==WildlifeUpload::Purpose::ML);
 }

 // Retain a single association across successive transfers, then shut down
 // after the idle grace period. Failed association remains bounded.
 assert(WildlifeUpload::sendRam(1794692281));events=false;
 WildlifeUpload::connecting=false;WildlifeUpload::radioOn=false;
 WiFi.begins=WiFi.disconnects=0;
 for(int n=0;n<5;++n){fakeUs+=1000000;assert(WildlifeUpload::tick("test","test",1794692281));assert(WildlifeUpload::tick("test","test",1794692281));}
 assert(WiFi.begins==1 && WiFi.disconnects==0 && mlCalls==5);
 mlWanted=false;fakeUs+=16000000;assert(!WildlifeUpload::tick("test","test",1794692281));assert(WiFi.disconnects==1);
 mlWanted=true;WiFi.fail=true;assert(WildlifeUpload::tick("test","test",1794692281));
 fakeUs+=12000000;assert(WildlifeUpload::tick("test","test",1794692281));assert(mlFailures==1 && !WildlifeUpload::connecting && !WildlifeUpload::radioOn);
 assert(store.ops==0);
 std::cout<<"GUARD4_UPLOAD_PASS hash_mismatch_retained=1 hash_match_acked=1 no_flash=1 ml_not_starved=1\n";
}
