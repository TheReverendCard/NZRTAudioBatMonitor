# Daytime sleep and wake test without a power meter

The v1.0.3 sleep candidate assumes a supply that stays on.  A power meter is not a prerequisite for testing reliable sleep, clock retention, wake-up and recording recovery.  Those functional tests cannot establish actual mA, Wh/day or battery lifetime.

## Short bench test, about three minutes

1. Use a spare/test SD card and a private copy of the candidate sketch.  Keep Wi-Fi settings and the same board, USB and OPI PSRAM settings as your working recorder.
2. Change `#define SLEEP_SELF_TEST 0` to `#define SLEEP_SELF_TEST 1`, then upload in daylight on the bench.  This is an explicit test mode that temporarily ignores the field recording schedule and writes test files.
3. Keep Serial Monitor available at 115200.  The test obtains NTP time and saves the usual ten-second startup WAV, then performs three cycles of roughly ten seconds awake and thirty seconds asleep.  Boot and signalling add some time.  The USB port may disappear/reappear during sleep; reconnect the monitor if needed.  This mode intentionally permits sleep while Serial Monitor is open.
4. After the third timer wake, the recorder saves another ten-second WAV in a `sleep_check_...` folder.  It then stays awake.  Look for `SELF_TEST PASS cycles=3 rtc_resume=1 time_retained=1 post_sleep_wav=1` in that folder's `session.txt`.  Confirm the WAV opens in AviaNZ and has the same sample rate and expected ultrasonic content as the initial startup WAV.  Use a consistent sound source if comparing the two recordings.
5. Compare the logged local clock with a phone/computer before and after.  The wake status should show `boot_time_source=RTC_RESUME`; a timer resume normally has no new `NTP result` line.  Compare the measured elapsed time with the sleep/awake sequence, allowing for boot, WAV saving and USB reconnect time.

If the test never reaches the final folder, repeated `startup_...` folders or `rtc_resume_rejected=1` suggest that retained state/time is not being restored.  A missing or invalid post-sleep WAV is a recording-recovery failure.  If the first NTP sync fails, it cannot yet test scheduled sleep and will report a time fault.  The final PASS reports that the internal state/audio checks succeeded, not that an external meter measured a low current.

Set `SLEEP_SELF_TEST` back to **0** and upload again before field use.  The self-test does not turn itself into normal overnight field mode.

## Normal daylight test

After cold boot and initial NTP sync during the normal daytime collection interval, the unit should give its brief three-flash safe indication and sleep, leaving the status LED off.  It should not create a startup recording during that interval.  The audio/SD startup check is deferred to the pre-night wake window.

In normal mode, an open Serial Monitor holds the unit awake for inspection.  Close the monitor to allow sleep.  To inspect it while asleep, reset it or power-cycle it in daylight and reconnect the monitor promptly; the cold-boot path then syncs NTP again.  The serial-port disconnect during deep sleep is expected.

Sleep does not physically disconnect the SD or microphone supply.  I2S is stopped, SPI is ended, the microphone clock is held low, SD and future LoRa chip-selects are held high, and the user LED is held off.  Any module power LED/regulator remains a possible hardware load.

## One complete day/night test

- Run the normal mode on the existing always-on USB supply, with Serial Monitor closed for sleep.
- Check that morning logs finish with the existing summary and session-end records.  Once that shutdown is complete, normal daytime has no SD writes.  Disconnect power before removing the card; reinsert it before restoring power.  The next pre-night warm-up begins five minutes before the configured recording start, so the collection interval ends there rather than at sunset itself.
- Check the next night's session header for RTC resume/cycle information, a recent NTP result/age and the full active CPU clock.  Confirm it started near the configured schedule and saved valid 96 kHz WAVs with the expected error counters.
- If convenient, observe a noon sync and the evening wake with the computer clock as a reference.  Over several hours, compare retained-clock time with external time to assess RTC drift.  Do not assume deep sleep has zero drift.

A valid retained clock permits the night to proceed if that day's Wi-Fi sync fails.  Normal operation attempts noon sync at most three times, fifteen minutes apart, and once in the pre-night window.  If a timer wake cannot validate RTC time/state, it follows the fresh-NTP path.  A full power loss also requires a fresh time source.

## What we can infer without an energy meter

Successful repeated timer wakes, retained timestamps, stopped interfaces and a valid post-sleep recording establish that the low-power control path works.  They do not prove the assembled SD/mic/regulator board's standby consumption.  Later, comparing runtimes on the same known battery pack with the sleep feature enabled/disabled can provide an approximate practical improvement, but it is less controlled than measuring Wh.

For planning only, a 20-second time-sync attempt averaging 0.5 W costs `0.5 × 20 / 3600 = 0.0028 Wh`.  Even four 35-second attempts at 1 W would total about 0.039 Wh/day.  These are hypothetical complete-system input powers/durations, not measured radio consumption.  A long continuous reconnection loop would cost more; daytime retries are bounded in the candidate.  If time is unavailable after a full power loss, cold-start retries remain necessary under the existing trustworthy-time policy.

For comparison, the earlier assumed awake daytime load of 0.1–0.25 W over twelve hours is 1.2–3 Wh.  Sleeping can remove much of the CPU contribution, while the powered SD module, regulators and microphone determine how much of that remains.  The example sync penalty is small compared with that provisional daytime budget.

ESP32's default RTC/system-time mechanism normally retains wall time through deep sleep.  Power-on reset loses it.  Clock drift, especially with the internal RC source and temperature changes, is the practical issue to test; reacquiring Wi-Fi after every ordinary timer wake is not required by the design.

Sources:  [ESP32-S3 system time](https://docs.espressif.com/projects/esp-idf/en/v5.2/esp32s3/api-reference/system/system_time.html), [sleep and RTC-memory retention](https://docs.espressif.com/projects/esp-idf/en/v5.5.3/esp32s3/api-reference/system/sleep_modes.html).

## USB meter comparison

Use the same supply, cable and meter for each comparison, with only the recorder downstream.  Disconnect Serial Monitor for normal daytime sleep.  Reset accumulated Wh if the meter supports it; otherwise photograph its starting and ending Wh and timer readings.  Compare a full 24-hour baseline with a full 24-hour sleep-enabled run under similar recording conditions.  Daily energy is the difference in Wh; average watts are Wh divided by elapsed hours.  A brief instantaneous current reading does not establish daily energy, and inexpensive meters may round sleeping current to zero.  Record a separate 15-minute daytime comparison and note WiFi sync duration from the log.

For adaptive sync, collect CLOCK log entries across several days.  Confirm cold power-up always syncs, timer wakes retain the interval, and low measured drift extends the interval beyond a day.  Deadlines during a recording night are brought forward to the pre-night guard.  Compare correction_seconds against the five-second target.  Large new drift must shorten the next interval.  These checks require the physical board; host tests cannot establish actual RTC drift.
