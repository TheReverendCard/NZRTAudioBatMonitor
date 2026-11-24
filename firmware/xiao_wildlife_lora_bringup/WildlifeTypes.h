#pragma once
#include <Arduino.h>

// Include before Arduino IDE generates function prototypes for the sketch.
// Keep the capture-counter wire schema independent of radio transports.
struct CaptureStats {
  uint64_t bytes = 0;
  uint64_t oneBits = 0;
  uint32_t goodBlocks = 0;
  uint32_t shortReads = 0;
  uint32_t readErrors = 0;
  uint32_t worstReadUs = 0;
  int lastReadError = 0;
};
