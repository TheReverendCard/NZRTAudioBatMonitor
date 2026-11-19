#include "WildlifeML.cpp"
#include <cassert>
#include <iostream>
SerialT Serial;Store store;FS SPIFFS;uint64_t fakeUs=1000000;
namespace WildlifeDetector {
unsigned passCurrent(){return 17;}bool requestPass(unsigned){return true;}
bool preparePass(unsigned){return true;}bool passApplied(unsigned){return true;}
const char* passName(unsigned){return "evolved";}void passStatus(char*b,size_t n){snprintf(b,n,"NZRT FIRST_PASS version=PASS-2");}
}
int main(){using namespace WildlifeML;
 assert(begin(123));wavEnabled=true;inferenceEnabled=true;
 Clip& c=clips[0];c.test=false;c.rawBench=false;c.n=TOTAL;c.wav=true;c.valid=true;c.run=1;c.seq=123;c.start=0;c.active=false;
 memset(c.pcm,0,TOTAL*2);c.state=READY;tick();
 assert(c.state==OWNED);assert(c.lease.delivery);assert(c.lease.score==RTClipLease::Waiting);
 // Receiver may ACK before scoring begins, but the score reader keeps PCM.
 assert(upload(c));c.lease.delivery=false;tick();assert(c.state==OWNED);
 assert(scoreOne(c));assert(c.valid);assert(c.lease.score==RTClipLease::Done);tick();assert(c.state==FREE);
 // Pressure cancels scoring while preserving a complete WAV for delivery.
 c.valid=true;c.n=TOTAL;c.state=READY;tick();RtWatch::sig().audioPressure=true;
 assert(scoreOne(c));assert(!c.valid);assert(!strcmp(c.scoreReason,"audio_pressure"));tick();assert(c.state==OWNED);assert(c.lease.delivery);
 c.lease.delivery=false;tick();assert(c.state==FREE);RtWatch::sig().audioPressure=false;
 // Off still delivers; no scoring job. Input gap/incomplete audio does not upload.
 inferenceEnabled=false;c.valid=true;c.n=TOTAL;c.state=READY;tick();assert(c.state==OWNED);assert(c.lease.score==RTClipLease::Reported);assert(c.lease.delivery);c.lease.delivery=false;tick();assert(c.state==FREE);
 c.valid=false;c.n=TOTAL/2;c.state=READY;tick();assert(c.state==FREE);
 // Network retries must not free a buffer being read by the scorer.
 inferenceEnabled=true;c.valid=true;c.n=TOTAL;c.state=READY;tick();assert(c.lease.claim());
 networkFailed();networkFailed();networkFailed();assert(c.lease.delivery);assert(c.attempts==0);tick();assert(c.state==OWNED);
 c.lease.delivery=false;
 c.valid=false;c.scoreReason="disabled";c.lease.score=RTClipLease::Done;tick();assert(c.state==FREE);
 // Deadline is independent of receiver state.
 ScoreBudget deadline(c);fakeUs+=30000001ULL;assert(!ScoreBudget::check(&deadline));assert(!strcmp(c.scoreReason,"deadline"));

 // A failed HTTP request does not block a different recording; retries retain
 // the failed recording and older due slots win regardless of array index.
 for(auto& item:clips)item.state=FREE;
 inferenceEnabled=false;wavEnabled=true;fetchHash[0]=0;nextControl=millis()+100000;
 auto ready=[&](Clip& q,uint32_t seq){q.test=false;q.rawBench=false;q.loadProbe=true;q.valid=true;q.n=TOTAL;q.wav=true;q.seq=seq;q.attempts=0;q.state=READY;tick();};
 ready(clips[3],103);fakeUs+=1000;ready(clips[0],104);
 httpWrongHash()=true;connected();assert(clips[3].attempts==1);assert(clips[0].attempts==0);assert(clips[3].lease.delivery);
 httpWrongHash()=false;connected();assert(!clips[0].lease.delivery);assert(clips[3].lease.delivery);
 fakeUs+=5000000;connected();assert(!clips[3].lease.delivery);tick();assert(idle());
 // Expiry is explicit and retains PCM while a score reader is in flight.
 inferenceEnabled=true;ready(c,105);assert(c.lease.claim());fakeUs+=300001000;
 tick();assert(!c.lease.delivery && c.state==OWNED);c.lease.score=RTClipLease::Done;tick();assert(c.state==FREE);
 // Runtime bench choices leave persistent user choices alone and restore them.
 inferenceEnabled=true;wavEnabled=false;activeMode=true;
 assert(loadCommand("start"));assert(loadActive && !benchRaw && !activeMode);
 assert(loadCommand("phase 0 1"));assert(!inferenceEnabled && wavEnabled);
 loadStop();assert(inferenceEnabled && !wavEnabled && activeMode && !bench);
 std::cout<<"GUARD4_WORKER_PASS early_wav=1 no_early_reuse=1 pressure_fallback=1 inference_off_wav_on=1 incomplete_rejected=1 settings_restore=1\n";
}
