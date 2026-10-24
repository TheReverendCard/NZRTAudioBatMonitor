# NZRT field pilot v3: boot-time and daily UTC synchronisation

**Status:** Experimental, not yet tested on the user's physical XIAO. This work does not alter the separate SD recorder (v1.0.3), the transit gateway or transit sign.

## Goals and clock sources
- With local Wi-Fi credentials present, attempt NTP shortly after each boot **and every 24 hours after the previous attempt finishes** (successful or timed out). It does not stay associated between attempts. A single cycle takes up to 12 seconds for Wi-Fi association and 12 seconds for NTP. Failed daily attempts retry at the next 24-hour interval, not in a tight loop. Timekeeping remains monotonic from the last valid time anchor between checks; time source and last sync age are visible in `nzrt time`.
- The device logs **every** successful `NZRT TIME_SYNC` refresh, even when no substantial correction was required. This provides an auditable time anchor at least daily when NTP is reachable. Use `nzrt time` for `attempts`, `last_attempt_uptime_s`, `last_sync_uptime_s`, and `next_wifi_attempt_in_s`.
- At boot, **start acoustic DSP and genuine MeshCore immediately**, as in the already-validated pilot. If Wi-Fi has been configured locally, begin a **non-blocking, maximum 12 s association and maximum 12 s NTP wait** after 3 seconds of boot. On successful SNTP update, set the MeshCore RTC and turn Wi-Fi OFF. Do not keep the Wi-Fi radio connected for the rest of the field run.
- If Wi-Fi is not configured, out of range or fails, **do not make up a wall clock**. Continue recording relative times with `time_source=UNSYNCED`, `utc_start=0`, and `utc_end=0`.
- **LoRa fallback:** The *pinned MeshCore v1.18.0* already provides the authenticated remote `clock sync` command from an authorised client. The NZRT time bridge observes a plausible **forward jump of >=30 seconds** to MeshCore's RTC and records a new anchor with `source=MESHCORE_REMOTE`. It can then timestamp future events, and estimate earlier events from the same session using detector uptime. This **does not implement autonomous RF time requests or a time-beacon**: a reachable, independently time-synchronised peer (e.g. future always-on house node) must send the remote clock sync request. Generic unauthenticated adverts and unrelated LoRa packets are not accepted as clock evidence. MeshCore's stock CLI does not permit moving its clock backwards via `clock sync`; a bad future clock needs careful administrative intervention.
- All absolute times in logs are **UTC Unix epoch seconds**, independent of local daylight savings. Use NZDT (UTC+13) only for presentation. Fields `utc_start`/`utc_end` on an event are approximate to 1s granularity; `from_ms`/`to_ms` stay available for timing within a session.

## Wi-Fi provisioning and privacy
Never commit or send private Wi-Fi credentials to GitHub or ChatGPT. Connect USB serial with `py -m serial.tools.miniterm COM8 115200 --eol CR`, local echo OFF, enter:

```text
nzrt wifi set YOUR_SSID|YOUR_WIFI_PASSWORD
```

The separator is a literal pipe `|`. Spaces in SSID/password are accepted; a literal pipe **inside** an SSID is not supported. The firmware masks the sensitive remainder of this particular command from **firmware USB serial echo**. The password is still transmitted in plaintext over local USB and stored in ESP32 NVS (no flash-encryption guarantee): only do this on a device you trust and avoid logging plaintext serial input in host software. The CLI never reports the credentials. `nzrt wifi clear` deletes the stored SSID and password. A new connection attempt happens on the next boot after provisioning. On power loss/reflash, ordinary firmware upload preserves NVS, barring an erase-flash operation. On `nzrt wifi set` while previously unconfigured, the device can also start a one-time connection after 3 seconds; a reboot remains the simplest full-cycle verification.

After entering credentials, unplug/replug power (or `reboot`), reconnect to serial, and inspect:

```text
nzrt time
nzrt status
clock
log
```

Desired:
- `NZRT TIME wifi=CONNECTING`, then `wifi=CONNECTED ntp=WAITING`, `NZRT TIME_SYNC source=WIFI_NTP utc=<epoch> uptime_ms=<ms>` and Wi-Fi switches OFF.
- `nzrt time` shows `status=SYNCED source=WIFI_NTP`, matching the real current UTC time, and `clock` shows the correct UTC MeshCore time. The same line shows the next scheduled Wi-Fi check; immediately after successful NTP it should be around 86,400 seconds away.
- `NZRT CANDIDATE` records include `utc_start`, `utc_end` and `time_source=WIFI_NTP`; `NZRT BAND` checkpoints include `utc`. A `NZRT SESSION` marker at boot is intentionally marked `time=UNSYNCED` until a separate `NZRT TIME_SYNC` anchor is logged.
- **Critically check microphone/DSP health when Wi-Fi is active:** first 60s `NZRT MIC` must keep `short=0`, `errors=0`, and `dsp_drop`/`dsp_gap` at 0. Some transient DSP overruns can occur without losing blocks. `legacy_rx_q_ovf` should not grow beyond startup baseline.
- The board must continue logging when no Wi-Fi is available. After a temporary field night, recover the session data with `log` and archive before any `log erase`.

## Update from existing local Windows PlatformIO project
The earlier tested one-command PowerShell workflow still applies: the helper now fetches six source files, locally patches MeshCore `main.cpp` to add serial masking, `nzrt wifi set`, `nzrt wifi clear`, `nzrt time`, and includes `WildlifeTime.cpp` in `platformio.local.ini`. It backs up the original source and local build config and keeps the user's private `variants/xiao_s3_wio/platformio.ini` admin password unchanged. No change to the SD recorder's v1.0.3 code.

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TheReverendCard/NZRTAudioBatMonitor/exp/meshcore-wildlife-repeater/firmware/meshcore_wildlife/apply_nzrt_detector_update.ps1" -OutFile "$env:TEMP\nzrt-update.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\nzrt-update.ps1"
```

The helper is meant to fail before source replacement if the local file anchors are different. If it fails, preserve its backup and report the error; do not download unrelated ZIPs or re-edit the private admin password. Compiler/CI success is distinct from actual USB, Wi-Fi, audio and LoRa coexistence testing.

## Future enhancements
- A **house MeshCore node** with access to a trusted clock can send remote `clock sync`; on-site autonomous time acquisition over LoRa requires a designed protocol or supported MeshCore requester and a trusted service/peer. Do not synchronise from arbitrary RF packet timestamps.
- In a later revision, adopt bounded/rotating flash logs and better bat pulse-shape/sequence checks. The current candidate threshold is **not a species classifier**.

## Daily recheck validation

After initial on-device NTP success, confirm `nzrt time` shows `wifi=OFF`, `attempts=1`, `last_sync_uptime_s` populated and `next_wifi_attempt_in_s` close to `86400`. Serial should report no further `wifi=CONNECTING` during a normal 15–30-minute smoke test. The **24-hour delayed retry itself remains untested on hardware** until a full day has elapsed. Observe processing health during each NTP connection: `dsp_drop`, `dsp_gap`, and audio read errors should remain near zero. On power-up outside Wi-Fi coverage, it will attempt once and close the radio; after 24 hours it will try again. In parallel, MeshCore may accept a remote `clock sync` if an authorised reachable client transmits one; this is **not an autonomous LoRa time request**. Without an NTP or authenticated MeshCore update, keep timestamps `UNSYNCED` and use relative uptime data.
