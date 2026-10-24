#pragma once
#include <Arduino.h>

// Whangarei daylight mic-standby policy.
// Automatic schedule is fail-open: unknown UTC means capture stays ON.
namespace WildlifeDay {
void begin();
void tick();
void printStatus();
void testSleep(); // 90-second safe test override
void testWake();  // 90-second safe test override
void autoMode();
void setScheduleEnabled(bool enabled);
}
