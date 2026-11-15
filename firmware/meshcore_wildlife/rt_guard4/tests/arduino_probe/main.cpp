// Integration link harness only. No MeshCore, time or solar scheduling implementation.
// NOT a device update. The actual updater builds in the owner's full source project.
#include <Arduino.h>
#include <SPIFFS.h>
#include "WildlifeMic.h"
#include "WildlifeML.h"
#include "WildlifeUpload.h"
void setup(){Serial.begin(115200);SPIFFS.begin(false);WildlifeMic::begin();}
void loop(){WildlifeMic::printHealthIfDue();WildlifeML::tick();WildlifeUpload::tick("","",0);delay(1);}
