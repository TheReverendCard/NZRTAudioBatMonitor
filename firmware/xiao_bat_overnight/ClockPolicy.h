#pragma once
#include <stdint.h>
#include <math.h>
namespace RecorderClock {
constexpr uint32_t DAY=86400, MIN_INTERVAL=900, MAX_INTERVAL=7*DAY;
// Four seconds of drift budget leaves one second for sync uncertainty.
// Double the worst observed rate; never learn from a short retry interval.
inline uint32_t interval(int64_t elapsed,double correction,uint32_t &worstPpb,uint32_t previous) {
  if(elapsed<3600 || !isfinite(correction))return previous;
  double rate=(fabs(correction)+0.25)*1e9/double(elapsed);
  uint32_t ppb=rate>=4000000000.0?4000000000u:uint32_t(ceil(rate));
  if(ppb>worstPpb)worstPpb=ppb;
  double seconds=4e9/(2.0*worstPpb);
  uint32_t result=seconds<MIN_INTERVAL?MIN_INTERVAL:seconds>MAX_INTERVAL?MAX_INTERVAL:uint32_t(seconds);
  // Grow by at most 2x per successful observation; shrink immediately.
  return result>previous*2?previous*2:result;
}
inline int64_t attemptAt(int64_t now,int64_t due,int64_t lastAttempt,bool lastOK,
                         uint32_t attempts,bool sameDay) {
  if(!lastOK && sameDay && attempts>=3)return now+86400;
  return !lastOK && lastAttempt+900>due?lastAttempt+900:due;
}
}
