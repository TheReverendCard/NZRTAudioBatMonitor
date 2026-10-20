#include <cassert>
#include <cstdint>
#include "../firmware/xiao_bat_overnight/CpuPowerPolicy.h"

int main() {
  CpuPowerPolicy policy;
  uint32_t actual = 240;
  uint32_t calls = 0;
  auto read = [&](){return actual;};
  auto set = [&](uint32_t mhz){++calls;actual=mhz;return true;};
  policy.begin(actual,80,true);
  assert(policy.updateIdle(true,read,set) && actual==80);
  for(int i=0;i<100;i++)assert(policy.updateIdle(true,read,set));
  assert(calls==1); // No repeated clock switches in the daytime loop.
  assert(policy.requireActive(read,set) && actual==240);
  assert(policy.updateIdle(true,read,set) && actual==80);
  assert(policy.updateIdle(false,read,set) && actual==240); // USB/unsafe idle gate.
  policy.begin(160,80,true);actual=160;
  assert(policy.updateIdle(true,read,set) && actual==80);
  assert(policy.requireActive(read,set) && actual==160); // Restore the actual boot clock.
  policy.begin(240,80,false);actual=240;
  assert(policy.updateIdle(true,read,set) && actual==240);
  policy.begin(80,80,true);actual=80;
  assert(policy.updateIdle(true,read,set) && actual==80);
  policy.begin(240,40,true);actual=240;
  assert(policy.updateIdle(true,read,set) && actual==240); // Never choose a sub-80MHz idle clock.
  policy.begin(240,80,true);actual=240;
  auto refuse = [&](uint32_t){return false;};
  auto failures=policy.failures();
  assert(!policy.updateIdle(true,read,refuse) && actual==240);
  assert(policy.failures()==failures+1);
  actual=80;
  assert(!policy.requireActive(read,refuse) && actual==80); // Callers must defer active work.
  auto misreport = [&](uint32_t){return true;};
  assert(!policy.requireActive(read,misreport)); // Verify readback, not just the return code.
}
