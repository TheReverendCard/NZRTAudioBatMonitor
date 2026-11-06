#pragma once
#include <stdint.h>
#include <stddef.h>
#include "WildlifeScoring.h"
// Experimental, unclassified 18-45 kHz activity, NOT bat identification.
// Expects 3.072 MHz STD/MSB raw PDM little-endian stereo16 word chronology.
namespace WildlifeDetector {
struct Event {
  uint32_t seq,start_ms,end_ms,run,start_uptime_ms,end_uptime_ms;
  float peak_ratio;
  WildlifeScoring::Features features;
  // 0=normal, 1=input gap, 2=run stopped, 3=10-second event limit.
  uint8_t ended_reason;
};
struct Snapshot {
  uint32_t windows,candidates;
  float band_rms,noise_rms,peak_ratio;
  uint32_t bat_like,uncertain,event_queue_lost,input_gaps;
};
void reset(uint32_t run=0,uint32_t originUptimeMs=0);
void onInputGap(uint32_t missingBlocks);
void consume(const uint8_t* data,size_t bytes,uint32_t captureEndUptimeMs=0);
#ifdef NZRT_HOST_TEST
void consumePcmForTest(const float* pcm,size_t samples);
#endif
bool pop(Event& event);
void snapshot(Snapshot& out);
}
