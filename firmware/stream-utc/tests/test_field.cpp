#include <cassert>
#include <initializer_list>
#include "../XiaoStream/field.h"
#include "../XiaoStream/pulse_train.h"

using pulse_train::Detector;
using pulse_train::scoreFloor;

static void quiet(Detector& detector, unsigned frames) {
    while (frames--) assert(!detector.update(scoreFloor - 1));
}

static void testPulseTrain() {
    Detector detector;
    for (int i = 0; i < 750; ++i) assert(!detector.update(1800));
    quiet(detector, 7);
    assert(!detector.update(scoreFloor));
    quiet(detector, 8);
    assert(!detector.update(scoreFloor));  // First fresh onset after a sustained signal.
    quiet(detector, 8);
    assert(!detector.update(scoreFloor));
    quiet(detector, 8);
    assert(detector.update(scoreFloor));
    assert(!detector.update(scoreFloor));

    // Three onsets including the exact 187-frame boundary, then one frame beyond.
    for (unsigned last : {187U, 188U}) {
        detector.reset();
        assert(!detector.update(scoreFloor));
        quiet(detector, 89);
        assert(!detector.update(scoreFloor));
        quiet(detector, last - 91);
        assert(detector.update(scoreFloor) == (last == 187));
    }
    // A capture discontinuity discards both earlier onsets.
    detector.reset();
    assert(!detector.update(scoreFloor));
    quiet(detector, 8);
    assert(!detector.update(scoreFloor));
    detector.reset();
    assert(!detector.update(scoreFloor));
}

int main() {
    testPulseTrain();
    assert(!field::daytimeRemaining(0));
    // 24 Nov 2026 00:00 UTC is early afternoon in Whangarei.
    const int64_t noon=1795478400;
    auto left=field::daytimeRemaining(noon);
    assert(left>5*3600 && left<9*3600);
    assert(field::daytimeRemaining(noon+left-1)==1);
    assert(!field::daytimeRemaining(noon+left));
    assert(!field::daytimeRemaining(noon+12*3600));
    // At winter local noon and midnight.
    assert(field::daytimeRemaining(1782000000)>0);
    assert(!field::daytimeRemaining(1782000000+12*3600));
}
