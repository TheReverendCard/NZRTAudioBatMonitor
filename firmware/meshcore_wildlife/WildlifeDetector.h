#pragma once
#include <stdint.h>
#include <stddef.h>
// Experimental, unclassified 18-45 kHz activity, NOT bat identification.
// Expects 3.072 MHz STD/MSB raw PDM little-endian stereo16 word chronology.
namespace WildlifeDetector {
struct Event { uint32_t seq,start_ms,end_ms; float peak_ratio; };
struct Snapshot { uint32_t windows,candidates; float band_rms,noise_rms,peak_ratio; };
void reset();
void consume(const uint8_t* data,size_t bytes);
bool pop(Event& event);
void snapshot(Snapshot& out);
}
