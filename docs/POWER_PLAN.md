# Recorder power plan and next firmware candidate

20 October 2026.  No measured daily energy baseline exists yet.  The earlier 5–10 Wh/day estimate is a provisional complete-system planning range, not a battery-runtime guarantee.

## Prioritised work

| Priority | Feature request | Expected benefit and constraint |
| --- | --- | --- |
| P1 | [Measure the complete 24-hour energy budget #2](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/2) | Establish Wh/day and peak current before selecting the battery or claiming savings. |
| P1, selected next | [Reduce daytime idle CPU frequency #3](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/3) | Small firmware change; reduces CPU activity cost during daylight while retaining the existing collection and USB workflow.  Savings need measurement. |
| P2 | [Scheduled daytime sleep #4](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/4) | Likely greater daytime saving; requires reliable wake-up, RTC/time trust, collection indication and power-bank compatibility. |
| P2 | [Peripheral standby audit and power switching #5](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/5) | Addresses SD, mic, regulator and LED loads that CPU changes alone cannot remove.  Hardware-dependent. |
| P3 | [Night DSP and active-clock benchmarking #6](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/6) | Targets continuous overnight energy without losing pretrigger or introducing unrecorded listening gaps. |
| P3 | [Battery health and energy-aware telemetry #7](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/7) | Supports safe unattended battery/solar operation and measured reserve planning. |

Wi-Fi is already disabled before capture and used only for clock synchronisation.  No new radio saving is claimed for doing that again.  Reducing event file counts is not assumed to remove the continuous microphone and DSP cost.  Do not add intermittent listening or remove audit samples to manufacture a lower power figure.

## Selected v1.0.2 candidate

The candidate in `firmware/xiao_bat_overnight` imports the existing project v1.0.1 overnight sketch and adds a small, configurable daytime CPU policy.  The source is prepared for the next firmware update; it is not deployed and has no measured power or real-board validation yet.

After the startup test, outside the night recording window, the CPU may reduce to 80 MHz only when:

- The clock is known and no configuration, session, storage or CPU-restoration fault is active.
- I2S/microphone capture is stopped, SD is unmounted, no log is open and the radio is off.
- Serial Monitor is disconnected.

The boot-selected active frequency is restored and checked before every Wi-Fi/NTP attempt and SD/session start.  Restoration failure defers that work and produces a fault indication.  The policy reads back the resulting clock and records switch attempts/failures.  It does not keep switching the clock every loop when the requested state is already active.  Serial Monitor connection requests the active clock, so take power measurements without a serial connection.

The implementation deliberately does not enter sleep, reduce the night clock, change the 3.072 MHz PDM clock, 96 kHz PCM, DSP/filter, event thresholds, clip lengths, pretrigger or five-minute periodic samples.  It leaves the three-flash daytime collection indication and existing power-off-before-removing-SD instructions intact.  80 MHz is not deep sleep; powered peripherals, CPU-independent loads and conversion losses remain.

Settings:

```cpp
constexpr bool ENABLE_DAYTIME_CPU_REDUCTION = true;
constexpr uint32_t DAYTIME_CPU_MHZ = 80;
```

Set the enable flag to false for an A/B comparison or to disable this feature without changing the capture configuration.  Keep the running v1.0.1 recorder as the reference until compilation and real-board checks pass.  Do not update a recorder in the middle of a field night.

## Verification before promotion

The host C++ policy test exercises a normal idle/active cycle, repeated idle updates, USB/unsafe-state restoration, 160 MHz boot-frequency restoration, disabled reduction, no-op 80 MHz configuration, invalid sub-80 MHz idle settings, refused switches and mismatched readback.  It does not simulate the ESP32 peripheral drivers or establish USB/timekeeping correctness.

The added CI workflow builds the whole sketch using Arduino ESP32 3.3.12, XIAO ESP32S3, OPI PSRAM, hardware CDC/JTAG, CDC enabled, 240 MHz and 8 MB flash.  A passing compile is required; it does not replace hardware tests.  If using a different USB mode, compile and test that mode separately.

On the actual board, verify:

1. Boot/NTP and the startup WAV; inspect audio, hashes and existing error counters.
2. Daytime disconnected from USB data: safe indication, reduced CPU state and lower measured current.  Status after USB connection should report the restored active frequency and nonzero transition count.
3. Noon NTP success/failure, repeat retries, USB reconnect and clock restoration before SD remount.
4. Day-to-night transition at the configured schedule, then a complete night.  Confirm the full active CPU clock in the session POWER line, sample continuity, no new capture errors and valid 96 kHz WAVs.
5. Compare at least a full night plus daylight with reduction disabled/enabled, reporting Wh and supply details.  Reject the candidate if the power bank shuts off or capture/USB reliability changes.

No battery life or saving percentage is established until that measurement is complete.

## Sources and credits

- [Arduino ESP32 3.3.12 CPU-frequency implementation](https://github.com/espressif/arduino-esp32/blob/3.3.12/cores/esp32/esp32-hal-cpu.c), including change return values and clock readback.
- [Arduino ESP32 3.3.12 XIAO board settings](https://github.com/espressif/arduino-esp32/blob/3.3.12/boards.txt).
- [ESP32-S3 power management](https://docs.espressif.com/projects/esp-idf/en/v5.5.6/esp32s3/api-reference/system/power_management.html).
- [USB Serial/JTAG sleep limitations](https://docs.espressif.com/projects/esp-idf/en/v5.1.5/esp32s3/api-guides/usb-serial-jtag-console.html); exact behaviour depends on the selected USB mode.

Microphone breakout credits remain with [meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU).  The imported sketch retains its existing capture/DSP references, including [AkiyukiOkayasu/pico-PDM](https://github.com/AkiyukiOkayasu/pico-PDM) and the Adafruit microSD BFF design reference.  The new CPU policy is an independent project implementation, not copied from those designs.
