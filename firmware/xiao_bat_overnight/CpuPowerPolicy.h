#pragma once
#include <stdint.h>

// Hardware-independent policy. Callers must guarantee that idleAllowed is true
// only with microphone, SD and radio stopped. No sleep or capture-time DFS.
class CpuPowerPolicy {
 public:
  void begin(uint32_t activeMHz, uint32_t idleMHz, bool enabled) {
    activeMHz_ = activeMHz;
    idleMHz_ = idleMHz;
    enabled_ = enabled;
  }
  uint32_t activeMHz() const { return activeMHz_; }
  uint32_t idleMHz() const { return idleMHz_; }
  bool enabled() const { return enabled_; }
  uint32_t attempts() const { return attempts_; }
  uint32_t failures() const { return failures_; }

  template <class Read, class Set>
  bool requireActive(Read read, Set set) { return apply(activeMHz_, read, set); }

  template <class Read, class Set>
  bool updateIdle(bool idleAllowed, Read read, Set set) {
    // Never raise the CPU clock above the established active setting.
    const bool reduce = enabled_ && idleAllowed && idleMHz_ >= 80 && idleMHz_ < activeMHz_;
    return apply(reduce ? idleMHz_ : activeMHz_, read, set);
  }

 private:
  template <class Read, class Set>
  bool apply(uint32_t target, Read read, Set set) {
    if (read() == target) return true;
    ++attempts_;
    if (!set(target) || read() != target) { ++failures_; return false; }
    return true;
  }
  uint32_t activeMHz_ = 240;
  uint32_t idleMHz_ = 80;
  bool enabled_ = false;
  uint32_t attempts_ = 0;
  uint32_t failures_ = 0;
};
