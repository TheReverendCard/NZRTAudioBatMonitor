#pragma once
#include <atomic>
#include <cstdint>
// Capture publishes immutable PCM before either reader is admitted.  Only
// the main loop retires the lease; neither HTTP nor scoring can free PCM.
struct RTClipLease {
  enum Score : uint8_t { Waiting, Running, Done, Reported };
  std::atomic<uint8_t> score{Reported};
  bool delivery = false; // main-loop owner only
  void publish(bool needsScore, bool needsDelivery) {
    delivery = needsDelivery;
    score.store(needsScore ? Waiting : Done);
  }
  bool claim() {
    uint8_t expected = Waiting;
    return score.compare_exchange_strong(expected, Running);
  }
  bool releasable() const { return !delivery && score.load() == Reported; }
};
