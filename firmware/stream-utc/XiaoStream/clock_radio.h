#pragma once
#include <RadioLib.h>
#include "stream_clock.h"

// Wio B2B wiring and RF profile from the project's Museum gateway bring-up.
class ClockRadio : public SX1262 {
public:
    ClockRadio(Module* m): SX1262(m) {}
    int16_t beginClock() {
        pinMode(38,OUTPUT); digitalWrite(38,HIGH);  // external switch in RX
#if RADIOLIB_VERSION_MAJOR == 8
        ConfigLoRa_t config;
        config.frequency=915000000; config.bandwidth=125000;
        config.spreadingFactor=9; config.codingRate=7; config.syncWord=0x12;
        config.preambleLength=8; config.power=10;
        tcxoVoltage=RadioLibTCXOVoltage_t::Voltage1V8;
        useRegulatorLDO=false;
        int16_t rc=SX1262::begin(config);
#elif RADIOLIB_VERSION_MAJOR == 7
        int16_t rc=SX1262::begin(915.0,125.0,9,7,0x12,10,8,1.8);
#else
#error "Use RadioLib 8.0.0 or 7.3.x for this Wio radio."
#endif
        if(rc==RADIOLIB_ERR_NONE) rc=setDio2AsRfSwitch(true);
        return rc;
    }
};
