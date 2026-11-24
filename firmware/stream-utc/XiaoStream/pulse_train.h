#pragma once
#include <cstdint>

// One update per valid 512-sample frame at 192 kHz. Thresholds are trial settings.
namespace pulse_train {
constexpr int scoreFloor = 702;
constexpr unsigned releaseFrames = 8;
constexpr unsigned windowFrames = 187;  // 498.7 ms between first and third onset.

class Detector {
    // Ages saturate outside the window, also representing empty history.
    unsigned older = windowFrames + 1, newer = windowFrames + 1;
    unsigned quiet = releaseFrames;

public:
    void reset() { *this = Detector{}; }

    bool update(int32_t score) {
        if (older <= windowFrames) ++older;
        if (newer <= windowFrames) ++newer;
        if (score < scoreFloor) {
            if (quiet < releaseFrames) ++quiet;
            return false;
        }
        const bool onset = quiet == releaseFrames;
        quiet = 0;
        if (!onset) return false;
        const bool threeOnsets = older <= windowFrames;
        older = newer;
        newer = 0;
        return threeOnsets;
    }
};
}
