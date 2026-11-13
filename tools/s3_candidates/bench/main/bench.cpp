#include "first_pass.hpp"
#include "esp_timer.h"
#include <cstdio>
#include <cstdlib>
#include <cinttypes>
static bat_s3::Audible audible;
alignas(16) static float pcm[3840];
extern "C" void app_main(){
 if(!audible.init()){std::puts("BLOCKED FFT tables");return;}
 uint32_t seed=19; int hits=0; int64_t worst=0,sum=0;
 // Synthetic diagnostic only; link and time the same ESP-DSP kernels as the exports.
 for(int j=0;j<200;j++){
  for(auto &v:pcm){seed=1664525*seed+1013904223;v=(float(int(seed>>16)-32768))/32768.f;}
  bool hot=false;auto t=esp_timer_get_time();
  if(!audible.check(pcm,hot)){std::puts("ERROR FFT");return;}
  auto dt=esp_timer_get_time()-t;sum+=dt;worst=std::max(worst,dt);hits+=hot;
 }
 std::printf("AUDIBLE synthetic n=200 mean_us=%" PRId64 " max_us=%" PRId64 " hits=%d memory_bytes=%u\n",sum/200,worst,hits,(unsigned)sizeof(audible));
}
