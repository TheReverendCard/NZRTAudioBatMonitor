#pragma once
#include <Arduino.h>
#include <Mesh.h>

// Field-pilot time bridge. UTC only; Wi-Fi NTP is primary. A later
// authenticated MeshCore remote 'clock sync' can provide the fallback.
namespace WildlifeTime {
void begin(mesh::RTCClock& meshClock);
void tick(mesh::RTCClock& meshClock);
void printStatus();
void configureWiFi(const char* args); // SSID|PASSWORD; credentials never echoed/logged
void clearWiFi();
uint32_t epochForUptime(uint32_t uptimeMs); // 0 = UNSYNCED; 1s precision
const char* source();
bool valid();
}
