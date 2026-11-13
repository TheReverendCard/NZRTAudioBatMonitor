// Exercise the exact supervisor task under real FreeRTOS with a scaled test clock.
// Actual esp_restart and RTC retention; injected data counters, no microphone.
#include "GuardSignals.h"
#include "esp_attr.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <cstdio>
#include <cstdlib>
static bool dayStandby=false,captureEnabledRequest=true,dspEnabledRequest=true;
static uint32_t dspRunNumber=1;
static std::atomic<uint32_t> testElapsed{0};
static uint32_t millis(){return testElapsed.load();}
namespace WildlifeML {unsigned compareStage(){return 0;}}
#include "guard_task.inc"
extern "C" void app_main(){
 const bool recovered=esp_reset_reason()==ESP_RST_SW && RtGuard::valid(guardRTC);
 if(!recovered)guardRTC={0,0,0};
 guardPolicy.spent=recovered;
 if(recovered && guardRTC.reason!=RtGuard::DSP)abort();
 RtWatch::sig().forceLegacy.store(recovered);RtWatch::sig().ready=true;
 if(xTaskCreatePinnedToCore(guardTask,"guard",3072,nullptr,3,nullptr,1)!=pdPASS)abort();
 for(unsigned i=0;i<10;i++){
  RtWatch::bump(RtWatch::sig().rd);RtWatch::bump(RtWatch::sig().rep);
  RtWatch::bump(RtWatch::sig().win);
  // DSP completion counter deliberately frozen before and after recovery.
  testElapsed+=10000;vTaskDelay(pdMS_TO_TICKS(1100));
 }
 if(!recovered||!RtWatch::sig().forceLegacy||RtWatch::sig().fault!=RtGuard::DSP)abort();
 puts("NZRT_RESTART_GUARD_PASS retained_reason=DSP repeated_stall_no_reboot=1");fflush(stdout);
}
