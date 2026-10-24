#pragma once
#include <Arduino.h>

// Development-only microphone/mesh coexistence probe.
// These functions never inject messages into MeshCore.
namespace WildlifeMic {
bool begin();
void printHealthIfDue();
void printStatus();
void setDspEnabled(bool enable);
}
