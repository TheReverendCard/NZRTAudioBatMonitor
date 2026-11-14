#pragma once
#include <Arduino.h>
namespace WildlifeML {
bool begin(uint32_t session);
// Audio/DSP task only; no network, journal or allocation on these paths.
void pcm(float sample);
void trigger(uint32_t run,uint32_t seq,uint32_t triggerUptime);
void gap();
// Main loop only; network owner calls connected() after acquiring Wi-Fi.
void tick();
void status(Print& out=Serial);
bool command(const char* line);
bool wantsNetwork();
void connected();
void networkFailed();
}
