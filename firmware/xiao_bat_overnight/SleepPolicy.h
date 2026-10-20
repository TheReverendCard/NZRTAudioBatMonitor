#pragma once
#include <stdint.h>

namespace RecorderSleep {
constexpr uint32_t MAGIC=0x42545332; // BTS2
constexpr uint32_t VERSION=2;
constexpr int64_t EARLIEST_EPOCH=1704067200; // 2024-01-01 UTC
constexpr int64_t LATEST_EPOCH=4102444800;   // 2100-01-01 UTC
struct Checkpoint {
  uint32_t magic=0,version=0,checksum=0;
  int64_t sleepEpoch=0,wakeEpoch=0,lastSyncEpoch=0,lastAttemptEpoch=0;
  int64_t preSyncStart=0;
  uint32_t syncInterval=86400,driftPpb=0;
  int32_t lastAttemptDate=-1,noonDate=-1;
  uint32_t lastSyncOK=0,bootTestDone=0,failedSyncs=0,noonAttempts=0;
  uint32_t cycles=0,testStage=0,testCompleted=0,testMode=0;
};
inline uint32_t checksum(const Checkpoint &c) {
  uint32_t h=2166136261u;
  const uint64_t fields[]={c.magic,c.version,uint64_t(c.sleepEpoch),uint64_t(c.wakeEpoch),
    uint64_t(c.lastSyncEpoch),uint64_t(c.lastAttemptEpoch),uint64_t(c.preSyncStart),
    uint64_t(c.lastAttemptDate),uint64_t(c.noonDate),c.lastSyncOK,c.bootTestDone,
    c.syncInterval,c.driftPpb,c.failedSyncs,c.noonAttempts,c.cycles,c.testStage,c.testCompleted,c.testMode};
  for(uint64_t n:fields)for(unsigned i=0;i<8;++i){h=(h^uint8_t(n))*16777619u;n>>=8;}
  return h;
}
inline void seal(Checkpoint &c){c.magic=MAGIC;c.version=VERSION;c.checksum=checksum(c);}
inline bool valid(const Checkpoint &c,int64_t now,bool timerWake,bool selfTest) {
  return timerWake && c.magic==MAGIC && c.version==VERSION && c.checksum==checksum(c) &&
    c.syncInterval>=900 && c.syncInterval<=7*86400 &&
    c.testMode==uint32_t(selfTest) && c.sleepEpoch>=EARLIEST_EPOCH && c.sleepEpoch<LATEST_EPOCH &&
    c.wakeEpoch>c.sleepEpoch && c.wakeEpoch-c.sleepEpoch<=6*3600 &&
    c.lastSyncEpoch>=EARLIEST_EPOCH && c.lastSyncEpoch<=c.sleepEpoch+2 &&
    now>=c.sleepEpoch-2 && now<=c.wakeEpoch+3600 && now<LATEST_EPOCH;
}
// Choose the earliest useful wake, including a guard before recording. A zero
// result means remain awake (recording/guard period or an already-due task).
inline int64_t wakeAt(int64_t now,int64_t start,int64_t noon,int64_t retry,int64_t guard) {
  if(start-now<=guard)return 0;
  int64_t wake=start-guard;
  if(noon>0 && noon<wake)wake=noon;
  if(retry>0 && retry<wake)wake=retry;
  if(wake<=now+2)return 0;
  if(wake>now+6*3600)wake=now+6*3600;
  return wake;
}
} // namespace RecorderSleep
