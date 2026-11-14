#pragma once
#include "Arduino.h"
using TaskHandle_t=void*;using portMUX_TYPE=int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)0)
#define portEXIT_CRITICAL(p) ((void)0)
#define pdMS_TO_TICKS(n) (n)
#define pdPASS 1
