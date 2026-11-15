#include "WildlifeUpload.h"
#include <cassert>
#include <iostream>
SerialT Serial;Store store;FS SPIFFS;uint64_t fakeUs=30000000;
namespace WildlifeMic {
bool hasLiveEvents(){return true;}size_t formatLiveBatch(char*b,size_t n){snprintf(b,n,"NZRT FIELD test=1\n");return 1;}void ackLiveBatch(size_t){}
}
namespace WildlifeML {
bool wantsNetwork(){return true;}bool testUploadDue(){return false;}void connected(){}void networkFailed(){}
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
 assert(store.ops==0);
 std::cout<<"GUARD4_UPLOAD_PASS hash_mismatch_retained=1 hash_match_acked=1 no_flash=1 ml_not_starved=1\n";
}
