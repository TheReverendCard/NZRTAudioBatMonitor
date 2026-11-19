#pragma once
#include "Arduino.h"
#include "WiFi.h"
#include "SPIFFS.h"
#include "Stream.h"
inline bool& httpWrongHash(){static bool v=false;return v;}
struct HTTPClient {
 String hash;
 void setConnectTimeout(int){}void setTimeout(int){}
 bool begin(WiFiClient&,const String&){return true;}
 void addHeader(const char*k,const String&v){if(!strcmp(k,"X-FNV1a"))hash=v;}
 int GET(){return 204;}int getSize(){return 0;}
 String getString(){return httpWrongHash()?String("wrong hash"):String(std::string("OK ")+hash);}
 int POST(const String&){return 200;}int POST(uint8_t*,size_t){return 200;}
 int sendRequest(const char*,Stream*,size_t){return 200;}
 int writeToStream(File*){return 0;}void end(){}
};
