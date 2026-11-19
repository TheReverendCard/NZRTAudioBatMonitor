#pragma once
struct WiFiClient {};

#define WL_CONNECTED 3
#define WIFI_OFF 0
#define WIFI_STA 1
struct WiFiType {unsigned begins=0,disconnects=0;bool fail=false;void disconnect(bool){++disconnects;}void mode(int){}void setSleep(bool){}void begin(const char*,const char*){++begins;}int RSSI(){return -55;}int status(){return fail?0:WL_CONNECTED;}};static WiFiType WiFi;
