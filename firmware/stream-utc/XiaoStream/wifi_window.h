#pragma once
#include <stdint.h>

// The main loop owns the station. Call demand only for eligible queue entries.
struct WifiWindow {
    bool bootClock=true, on=false;
    int64_t started=0, retryAt=0, workUntil=0, totalMs=0;
    uint32_t starts=0;
    void demand(int64_t now) { workUntil=now+500; }
    bool shouldStart(int64_t now) const {
        return !on && now>=retryAt && (bootClock || now<workUntil);
    }
    void start(int64_t now) { started=now; on=true; ++starts; }
    bool shouldStop(int64_t now,bool connected,bool clockKnown) const {
        if(!on) return false;
        if(!connected && now-started >= (bootClock?20000:12000)) return true;
        if(bootClock && !clockKnown && now-started<20000) return false;
        return now>=workUntil;
    }
    void stop(int64_t now,bool connected) {
        totalMs+=now-started; on=false; bootClock=false;
        if(!connected) retryAt=now+300000;
    }
    int64_t elapsed(int64_t now) const { return totalMs+(on?now-started:0); }
};

// Keep the first fallback window long enough to hear successive clock packets.
// The non-round repeat interval sweeps the phase of regular gateway broadcasts.
inline bool wantClockRx(int64_t now, bool known, int64_t anchorUp) {
    int64_t age=known?now-anchorUp-3600000:now;
    return age>=0 && age%617000<135000;
}
