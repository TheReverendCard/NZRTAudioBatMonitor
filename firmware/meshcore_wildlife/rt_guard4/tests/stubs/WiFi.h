#pragma once
struct WiFiClient {};

#define WL_CONNECTED 3
#define WIFI_OFF 0
#define WIFI_STA 1
struct WiFiType {void disconnect(bool){}void mode(int){}void setSleep(bool){}void begin(const char*,const char*){}int status(){return WL_CONNECTED;}};static WiFiType WiFi;
