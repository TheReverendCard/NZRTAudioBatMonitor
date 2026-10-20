# XIAO overnight recorder, v1.0.3 sleep candidate

This imports the project's existing v1.0.1 overnight pilot and adds scheduled daytime deep sleep and retained-clock recovery.  It is a candidate for the next update, not a tested field release.  See [the power plan](../../docs/POWER_PLAN.md) for issue priorities, behaviour, limitations and acceptance checks.

Open `xiao_bat_overnight.ino` in Arduino IDE with `CpuPowerPolicy.h` in the same sketch folder.  Use Arduino ESP32 **3.3.12**, board **XIAO ESP32S3**, **OPI PSRAM**, **USB CDC On Boot enabled**, and the same USB mode as the established device.  CI checks hardware CDC/JTAG at 240 MHz.  Enter local Wi-Fi credentials in a private copy only; never commit them.  No additional Arduino libraries are required.

Wiring is unchanged: microphone CLK3/DATA4/SELECT low; GPIO5 dummy WS unconnected.  SD SCK7/MISO8/MOSI9/CS43 at 4 MHz.  Future LoRa CS41 is held high.  Keep the original shutdown/SD collection instructions in the sketch header.

The host policy test can be run from the repository root:

```sh
g++ -std=c++11 -Wall -Wextra -Werror tests/cpu_power_policy_test.cpp -o /tmp/cpu-policy-test
/tmp/cpu-policy-test
```

The test does not compile or emulate the entire Arduino sketch.  Real-board USB, scheduling, SD recovery and energy measurements remain necessary before flashing the next routine field version.

The preferred normal configuration has `ENABLE_DAYTIME_SLEEP = true` and `SLEEP_SELF_TEST = 0`.  A cold daytime boot syncs time and sleeps without mounting SD; the initial ten-second audio check is deferred to the pre-night warm-up.  Daytime sleep stops the LED, microphone clock and digital interfaces; it does not physically disconnect peripheral supply rails.

Use the [short sleep test](../../docs/SLEEP_TEST.md) without a power meter.  `SLEEP_SELF_TEST = 1` intentionally writes test WAVs and sleeps three times for thirty seconds, with ten-second awake windows.  It then saves a post-sleep WAV and stays awake.  Return the setting to zero and upload again for field use.
