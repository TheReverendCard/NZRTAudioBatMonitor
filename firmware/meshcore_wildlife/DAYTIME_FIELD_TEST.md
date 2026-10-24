# NZRT-FIELD-PILOT-4: bat-only daytime microphone standby bench checklist

**Scope:** experimental Whangārei/Maunu bat monitor with attached XIAO ESP32-S3, Wio SX1262 and ultrasonic PDM microphone. This update does **not** support physical module discovery, trap/bird function selection or deep sleep. A future architecture for these options is [MODULAR_DEPLOYMENT_PROFILES.md](../../docs/MODULAR_DEPLOYMENT_PROFILES.md).

## Current selected profile

- Bat acoustic sampling: enabled by default for this existing bat-only prototype. Target window is **30 minutes before calculated sunset until 30 minutes after calculated sunrise** in the Whangārei area (approximate coordinates 35.73° S, 174.32° E), recalculated every 30 seconds using NZST/NZDT.
- Outside that window, the reader task stops **I2S bitclock** and the DSP worker waits. The ESP32, SPIFFS journal, USB serial, MeshCore LoRa receiver/repeater and NTP clock scheduler remain running; the microphone 3.3 V rail may still be powered. This is **sensor standby**, not CPU deep sleep.
- If UTC is not synchronised, or sun position is indeterminate, fail open: leave the microphone sampling rather than risk missing bats.
- Each state change writes an `NZRT DAY_MODE` marker to serial and SPIFFS `/packet_log`, including UTC, uptime and requested capture state; a new DSP run number accompanies a wake so times can be aligned. Subsequent logs indicate `mode=DAY_STANDBY` or `mode=MONITORING` and capture on/off.
- Local NVS persists **`nzrt day enable`** (current bat schedule) or **`nzrt day disable`** (always-on mic, useful for another deployment/test). This is a first step toward user-selectable profiles, not a full module configuration UI.
- Temporary local bench commands `nzrt day test sleep` and `nzrt day test wake` each apply for **90 seconds**, then revert to auto. `nzrt day auto` ends the temporary override. `nzrt day` prints current state, clock validity and computed approximate sunrise and sunset in local minutes since midnight.

## Upload from existing Windows project

Close any open serial monitor. Run:

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TheReverendCard/NZRTAudioBatMonitor/exp/meshcore-wildlife-repeater/firmware/meshcore_wildlife/apply_nzrt_detector_update.ps1" -OutFile "$env:TEMP\nzrt-update.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\nzrt-update.ps1"
```

The helper updates new `WildlifeDay.cpp/h`, the existing microphone/clock modules, and the local MeshCore source hooks, backing up prior copies, while preserving the stored network credentials and local private radio password. Do **not** upload unless the pinned MeshCore CI compile has passed and the script reports `SUCCESS`.

## First on-device test (before outdoor deployment)

1. Check `nzrt time` is **SYNCED** and identifies `WIFI_NTP` or `MESHCORE_REMOTE`; if UNSYNCED, the safe default is mic ON regardless of local time.
2. Enter `nzrt day`: verify date/solar boundaries and schedule enabled, appropriate to local NZ time. `nzrt status` should show `NZRT-FIELD-PILOT-4`.
3. Enter `nzrt day test sleep`; verify a new `NZRT DAY_MODE state=STANDBY` log, then an `NZRT ALIVE ... capture=OFF mode=DAY_STANDBY` message. `NZRT MIC` should show near-zero bytes/s after the transition, no repeated driver errors, and `NZRT BAND windows` should stop increasing.
4. Enter `nzrt day test wake` (or let the previous 90-second override end). Check `NZRT DAY_MODE state=MONITORING`, `NZRT DAY I2S=RESTARTED`, and `NZRT MIC ... capture=ON`. Verify `NZRT BAND windows` resumes advancing, `dsp_drop` and `dsp_gap` do not accumulate continuously, and `stats-packets` is responsive.
5. Enter `nzrt day auto`, then `nzrt day` again. At daytime hours with valid UTC the mode should be STANDBY; at night MONITORING. To temporarily force continuous recording, `nzrt day disable` persists the preference and leaves capture on; re-enable with `nzrt day enable`. If you change the setting, verify it survives a reboot.
6. Check flash `log` includes both transition markers, without erasing previous records; daily Wi-Fi time sync remains scheduled. Compare actual standby/current consumption with an inline USB power meter before making any battery-life claims.
7. Before relying on the schedule for a whole night, verify one naturally timed dusk wake and dawn standby. The 90-second overrides test functionality but **do not themselves verify astronomical scheduling**.

## User-module configuration design

See the [modular deployment profiles design](../../docs/MODULAR_DEPLOYMENT_PROFILES.md). Selection of bird/trap/bat capabilities and wall/solar/battery power supply, automatic daughterboard identification and web/phone setup are intended but **not implemented** in this field-pilot version. A trap-only leaf will need a much lower-power policy; a repeater cannot reliably receive MeshCore messages while the CPU/radio are in deep sleep.
