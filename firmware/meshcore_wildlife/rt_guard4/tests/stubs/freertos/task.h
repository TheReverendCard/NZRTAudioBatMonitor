#pragma once
#include "FreeRTOS.h"
inline void vTaskDelay(unsigned n){fakeUs+=uint64_t(n)*1000;}
inline int xTaskCreatePinnedToCore(void(*)(void*),const char*,int,void*,int,void**,int){return pdPASS;}
