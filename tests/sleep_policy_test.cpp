#include <cassert>
#include "../firmware/xiao_bat_overnight/SleepPolicy.h"
using namespace RecorderSleep;
int main() {
  const int64_t t=1792450000;
  Checkpoint c;
  c.sleepEpoch=t;c.wakeEpoch=t+30;c.lastSyncEpoch=t-60;
  c.lastAttemptEpoch=t-60;c.lastSyncOK=1;c.cycles=3;c.bootTestDone=1;
  seal(c);
  assert(valid(c,t+30,true,false));
  assert(!valid(c,t+30,false,false)); // Cold/brownout wake requires fresh NTP.
  assert(!valid(c,0,true,false)); // A lost wall clock is rejected.
  assert(!valid(c,t+30,true,true)); // Changing test/field mode cannot resume old state.
  c.cycles=4;assert(!valid(c,t+30,true,false)); // Corrupt/inconsistent checkpoint.
  c.cycles=3;seal(c);assert(valid(c,t+30,true,false));
  c.bootTestDone=0;seal(c);assert(valid(c,t+30,true,false)); // Cold daytime boot may defer SD test.
  c.wakeEpoch=t;seal(c);assert(!valid(c,t,true,false));
  c.wakeEpoch=t+7*3600;seal(c);assert(!valid(c,t+7*3600,true,false));
  c.wakeEpoch=t+30;c.testMode=1;seal(c);assert(valid(c,t+30,true,true));
  assert(wakeAt(t,t+8*3600,t+2*3600,0,300)==t+2*3600); // Noon before evening.
  assert(wakeAt(t,t+4*3600,0,0,300)==t+4*3600-300); // Pre-night guard.
  assert(wakeAt(t,t+8*3600,0,t+900,300)==t+900); // Failed noon attempt retries asleep.
  assert(wakeAt(t,t+8*3600,0,t,300)==0); // Due sync: do not sleep through it.
  assert(wakeAt(t,t+8*3600,0,0,300)==t+6*3600); // Bounded sleep checkpoint.
  assert(wakeAt(t,t+200,0,0,300)==0); // Already in pre-night warm-up.
  assert(wakeAt(t,t-1,0,0,300)==0); // Recording start is never slept through.
  assert(wakeAt(t,t+1000,t+1,0,300)==0);
}
