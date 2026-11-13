// Independent direct DFT on bins used by the actual rule, including band edges.
#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static void yieldBench(){vTaskDelay(1);}
#else
static void yieldBench(){}
#endif
static void fftProof(){
 static float x[960],powers[480];unsigned seed=331;
 for(int kind=0;kind<3;++kind){
  for(int t=0;t<960;++t){seed=1664525*seed+1013904223;
   x[t]=kind==0?float(int(seed>>16)-32768)/32768.f:kind==1?float(t==415):float(sin(2*3.141592653589793*172.38*t/960));}
  WildlifeDetector::spectrumForTest(x,powers);
  for(int k=10;k<225;++k){
   if(k>=75 && k<90)continue;
   if(!(k%16))yieldBench();
   double a=0,b=0;for(int t=0;t<960;++t){
    const double r=-2*3.141592653589793*k*t/960, v=x[t]*(.5-.5*cos(2*3.141592653589793*t/959));
    a+=v*cos(r);b+=v*sin(r);}
   double ref=a*a+b*b;
   require(fabs(powers[k]-ref)<=.00008*(1+ref),"real FFT disagrees with direct DFT");
  }
 }
}
static void tone(bool lowPulse,bool highPulse){
 static float lo[192],hi[192];static bool initialized=false;
 if(!initialized){for(int t=0;t<192;++t){lo[t]=float(sin(2*3.141592653589793*22*t/192));hi[t]=float(sin(2*3.141592653589793*41*t/192));}initialized=true;}
 for(int t=0;t<3840;++t){
  float bg=lo[t%192],call=hi[t%192];
  w[t]=(lowPulse?.12f:.02f)*bg+(highPulse && t<1600?.016f:.00008f)*call;
 }
 WildlifeDetector::consumePcmForTest(w,3840);
}
static unsigned trial(unsigned cfg,bool low,bool high,bool pressure,unsigned cost,bool expectFallback){
 WildlifeDetector::reset(333,100);
 require(WildlifeDetector::requestPass(cfg),"config refused");
 for(int i=0;i<165;i++){tone(false,false);if(!(i%32))yieldBench();}
 WildlifeDetector::guardPressure(pressure);WildlifeDetector::setCostForTest(cost);
 for(int i=0;i<4;i++)tone(low,high);
 for(int i=0;i<12;i++)tone(false,false);
 WildlifeDetector::setCostForTest(0);WildlifeDetector::guardPressure(false);
 WildlifeDetector::Event e;unsigned mask=0;
 while(WildlifeDetector::pop(e)){mask|=e.triggerMask;require(e.fallback==expectFallback,"fallback attribution");}
 return mask;
}
static void recall(){
 fftProof();
 require(!WildlifeDetector::requestPass(16) && !WildlifeDetector::requestPass(3) && !WildlifeDetector::requestPass(31),"invalid config");
 require(trial(0,false,false,false,0,false)==0,"quiet control");
 require(trial(0,false,true,false,0,false)==0,"legacy would already hear weak pulse");
 require(trial(17,false,true,false,0,false)==2,"evolved-only pulse not rescued");
 require(trial(8,false,true,false,0,false)==0,"shadow triggered recording");
 require(trial(1,true,false,false,0,false)==0,"selected-only mode unexpectedly rescued legacy");
 require(trial(17,true,false,false,0,false)==1,"assist failed to preserve legacy-only pulse");
 require(trial(1,true,false,true,0,true)==1,"backpressure lost baseline");
 require(trial(2,true,false,false,400,true)==1,"slow active FFT lost baseline");
 require(trial(1,true,false,false,400,true)==1,"slow active band bank lost baseline");
 require(trial(18,false,false,true,0,false)==0,"load manufactured a candidate");
 // After a real input gap and reacquisition, baseline can trigger while the
 // selected detector still warms; counter deltas discriminate missing coverage.
 WildlifeDetector::reset(334,100);require(WildlifeDetector::requestPass(1),"gap setup");
 for(int i=0;i<165;i++){tone(false,false);if(!(i%32))yieldBench();}
 WildlifeDetector::onInputGap(2);for(int i=0;i<2;i++)tone(true,false);
 for(int i=0;i<17;i++)tone(false,false);
 WildlifeDetector::Event e;require(WildlifeDetector::pop(e) && e.fallback && (e.triggerMask&1),"gap warmup lost call");
}
