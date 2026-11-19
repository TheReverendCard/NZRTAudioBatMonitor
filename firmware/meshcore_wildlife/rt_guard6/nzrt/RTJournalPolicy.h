#pragma once
#include <cstdint>
// Three failures within fifteen minutes open a fifteen-minute circuit.
// A successful append does not erase the failure-rate history.
struct RTJournalPolicy {
  static constexpr uint32_t WINDOW = 900000, COOL = 900000;
  uint32_t windowStart=0, count=0, until=0, trips=0;
  bool opened=false, started=false;
  bool blocked(uint32_t now) {
    if (opened && uint32_t(now-until) < 0x80000000u) {
      opened=false; count=0; started=false;
    }
    return opened;
  }
  void failure(uint32_t now) {
    if (blocked(now)) return;
    if (!started || uint32_t(now-windowStart)>=WINDOW) {
      started=true; windowStart=now; count=0;
    }
    if (++count>=3) { opened=true; until=now+COOL; ++trips; }
  }
};
