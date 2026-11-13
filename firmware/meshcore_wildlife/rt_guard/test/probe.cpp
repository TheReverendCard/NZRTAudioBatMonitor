#include "WildlifeDetector.h"
#include "GuardSignals.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <cstring>
static int checks=0;
static void require(bool ok,const char* why){
 if(!ok){std::printf("NZRT_GUARD_FAIL %s\n",why);std::abort();}
 ++checks;
}
static void supervisor(){
 using namespace RtGuard;
 for(unsigned n=1;n<=4;++n){
  Policy p;Inputs x={1,0,0,0,0,true,true};
  uint32_t start=0xfffffff0u;
  unsigned resets=0;
  for(unsigned sec=0;sec<400;++sec){
   x.read+=n!=1;x.dsp+=n!=2;x.windows+=n!=3;x.report+=n!=4;
   Decision d=p.sample(start+1000*sec,x);
   if(d.restart){++resets;require(unsigned(d.fault)==n,"different stall");require(sec==(n==4?180u:30u),"deadline/wrap");}
  }
  require(resets==1,"one reboot only");Policy boot;auto rec=record(Fault(n));boot.spent=valid(rec);
  require(boot.spent,"RTC validate");rec.inverse^=1;require(!valid(rec),"invalid RTC accepted");
  boot.sample(1000,x);require(!boot.sample(999000,x).restart,"reboot loop");
 }
 Policy p;Inputs x={1,0,0,0,0,false,true};
 for(unsigned t=0;t<300000;t+=1000)require(!p.sample(t,x).restart,"standby");
 x.enabled=true;x.expectWindows=false;
 for(unsigned t=300000;t<500000;t+=1000){++x.read;++x.dsp;++x.report;require(p.sample(t,x).fault==OK,"decode-only bench");}
 x.expectWindows=true;x.run++;require(!p.sample(550000,x).restart,"run grace");
 // No candidates or receiver ACKs are inputs: a quiet offline monitor remains healthy.
 for(unsigned t=551000;t<900000;t+=1000){++x.read;++x.dsp;++x.windows;++x.report;require(p.sample(t,x).fault==OK,"quiet; receiver inaccessible");}
}
static float w[3840];
static void feed(float amp){
 for(int i=0;i<3840;i++)w[i]=amp*((i%8<4)?1.f:-1.f);
 WildlifeDetector::consumePcmForTest(w,3840);
}
static bool detector(unsigned shadow,bool pressure){
 WildlifeDetector::reset(123,1000);
 WildlifeDetector::guardPressure(pressure);
 require(WildlifeDetector::requestPass(shadow),"config");
 for(int i=0;i<166;i++)feed(.001f);
 for(int i=0;i<6;i++)feed(.09f);
 for(int i=0;i<16;i++)feed(.001f);
 WildlifeDetector::Event e;require(WildlifeDetector::pop(e),"lost primary event");
 require(e.run==123 && (e.passConfig&3)==0 && e.start_ms<e.end_ms,"wrong primary");
 require(e.shadowIncomplete==(shadow!=0 && pressure),"missing optional coverage");
 require(!WildlifeDetector::pop(e),"extra event");return true;
}
#include "recall_probe.inc"
extern "C" int guard_suite(){
 recall();
 supervisor();
 require(!RtWatch::pressure(3,8)&&RtWatch::pressure(4,8)&&RtWatch::pressure(24,48),"queue watermark");
 detector(0,false);unsigned base=RtWatch::val(RtWatch::sig().held);
 detector(8,true);require(RtWatch::val(RtWatch::sig().held)>base,"shadow not shed");
 detector(12,true);detector(8,false);
 require(WildlifeDetector::requestPass(0),"legacy selection");
 RtWatch::sig().forceLegacy=true;
 require(!WildlifeDetector::requestPass(12),"safe boot loaded optional model");
 RtWatch::sig().forceLegacy=false;
 printf("NZRT_GUARD_PASS checks=%d\n",checks);return 0;
}
#ifdef ESP_PLATFORM
extern "C" void app_main(){guard_suite();fflush(stdout);}
#else
int main(){return guard_suite();}
#endif
