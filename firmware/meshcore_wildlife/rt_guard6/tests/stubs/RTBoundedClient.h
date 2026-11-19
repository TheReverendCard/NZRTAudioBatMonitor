#pragma once
#include "WiFi.h"
struct RTBoundedClient:WiFiClient {uint32_t sendCalls=0,blockedCalls=0,bytesSent=0;bool timedOut()const{return false;}};
