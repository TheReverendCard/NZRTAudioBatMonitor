# Recorder power plan and next firmware candidate

20 October 2026.  No measured daily energy baseline exists yet.  The earlier 5–10 Wh/day estimate is a provisional complete-system planning range, not a battery-runtime guarantee.

## Prioritised work

| Priority | Feature request | Expected benefit and constraint |
| --- | --- | --- |
| P1 | [Measure the complete 24-hour energy budget #2](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/2) | Establish Wh/day and peak current before selecting the battery or claiming savings. |
| Fallback | [Reduce daytime idle CPU frequency #3](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/3) | Optional fallback when sleep is disabled.  Scheduled sleep is now the preferred candidate for the always-on supply and eventual battery/solar design. |
| P1, selected next | [Scheduled daytime sleep #4](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/4) | Likely greater daytime saving; requires reliable wake-up, RTC/time trust, collection indication and power-bank compatibility. |
| P2 | [Peripheral standby audit and power switching #5](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/5) | Addresses SD, mic, regulator and LED loads that CPU changes alone cannot remove.  Hardware-dependent. |
| P3 | [Night DSP and active-clock benchmarking #6](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/6) | Targets continuous overnight energy without losing pretrigger or introducing unrecorded listening gaps. |
| P3 | [Battery health and energy-aware telemetry #7](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/7) | Supports safe unattended battery/solar operation and measured reserve planning. |

Wi-Fi is already disabled before capture and used only for clock synchronisation.  No new radio saving is claimed for doing that again.  Reducing event file counts is not assumed to remove the continuous microphone and DSP cost.  Do not add intermittent listening or remove audit samples to manufacture a lower power figure.

## Selected v1.0.3 candidate: daytime deep sleep

The supply is confirmed always-on USB, with direct battery/solar intended later.  Power-bank shutoff is not a deployment constraint for this candidate.  The previous clock-reduction-only approach is superseded by scheduled deep sleep; 80 MHz idle remains a fallback when sleep is explicitly disabled.

Normal mode now stops microphone/I2S and SPI, keeps SD unmounted, turns Wi-Fi off, holds microphone clock/SPI outputs in inactive states, and deep-sleeps with the LED off.  The normal daytime collection interval performs no SD writes, including after a cold daytime boot; the first audio/SD startup check is deferred to the pre-night warm-up.  The explicit bench self-test is an intentional exception.

A small checksum-protected RTC-memory checkpoint carries the clock's provenance, boot-test state, last sync information and sleep/test counters.  Only a valid timer wake accepts it.  Wall time normally continues through sleep using the ESP32 RTC.  Cold/power-loss or invalid-checkpoint wake follows the fresh-NTP path.  New boot-relative timing anchors are established after wake.

The unit wakes for noon sync and five minutes before the configured recording start, with a maximum six-hour sleep chunk.  Noon sync retries are bounded to three attempts fifteen minutes apart; there is one pre-night sync attempt.  A failed sync does not discard valid retained time or block the night.  RTC drift and wake margin need functional field checking.

The SD module and microphone remain electrically powered because no switched supply has been established.  This firmware shuts down their activity/interfaces.  Hardware power switching remains issue #5.

Key settings:

```cpp
constexpr bool ENABLE_DAYTIME_SLEEP = true;
constexpr uint32_t PRE_NIGHT_WAKE_SECONDS = 300;
#define SLEEP_SELF_TEST 0
```

An open Serial Monitor holds normal operation awake for inspection.  The separate short self-test intentionally sleeps despite a connected monitor, records before/after WAVs and reports the retained state and clock path.  See [SLEEP_TEST.md](SLEEP_TEST.md) for a roughly three-minute functional test and a full day/night check that do not require a power meter.

The continuous night capture loop, microphone/PCM rates, filter, trigger, pretrigger and audit sampling are unchanged.  The original morning close/flush/unmount sequence is completed before entering sleep.  GPIO holds are released and the hardware is reinitialised on wake.

## Verification and remaining measurement

Host tests cover daytime wake planning, due/retry tasks, the pre-night guard, bounded sleep length, cold-wake rejection, invalid RTC time, checksum corruption, field/test-mode changes and deferred startup-test state.  CPU-clock fallback tests remain.  CI compiles both normal and short self-test modes with Arduino ESP32 3.3.12, OPI PSRAM, hardware CDC/JTAG and USB CDC enabled.

No real device has been flashed or measured here.  Successful functional tests can establish sleep/wake, retained time, file integrity and resumed recording without a current meter.  They cannot quantify complete-system Wh/day.  The measurement issue stays open, but it does not block beginning functional sleep tests.

The earlier 5–10 Wh/day planning range is not revised into a lower claimed figure yet.  A hypothetical 20-second sync at 0.5 W costs only 0.0028 Wh; even four 35-second attempts at 1 W cost about 0.039 Wh/day, versus the previously assumed 1.2–3 Wh awake daytime budget.  Actual savings depend on the peripherals and regulator that remain powered.

## Sources and credits

- [Arduino ESP32 3.3.12 CPU-frequency implementation](https://github.com/espressif/arduino-esp32/blob/3.3.12/cores/esp32/esp32-hal-cpu.c), including change return values and clock readback.
- [Arduino ESP32 3.3.12 XIAO board settings](https://github.com/espressif/arduino-esp32/blob/3.3.12/boards.txt).
- [ESP32-S3 power management](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32s3/api-reference/system/power_management.html).
- [USB Serial/JTAG sleep limitations](https://docs.espressif.com/projects/esp-idf/en/v5.1.5/esp32s3/api-guides/usb-serial-jtag-console.html); exact behaviour depends on the selected USB mode.

Microphone breakout credits remain with [meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU).  The imported sketch retains its existing capture/DSP references, including [AkiyukiOkayasu/pico-PDM](https://github.com/AkiyukiOkayasu/pico-PDM) and the Adafruit microSD BFF design reference.  The new CPU policy is an independent project implementation, not copied from those designs.
