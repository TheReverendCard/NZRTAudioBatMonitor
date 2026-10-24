# Field pilot: NZRT ultrasonic activity / MeshCore node

**Status:** Experimental. This build is a **candidate ultrasonic activity counter**, not a verified bat detector, acoustic species classifier, or live-network reporting device. The 18–45 kHz band was chosen for the New Zealand monitoring trial; >60 kHz noise research, Wi-Fi/WAV upload and sensor-originated LoRa packet transmission are deferred.

## Verified before this revision
- On bench with the same XIAO S3 + Wio SX1262 + SPH0641LU4H-1, 3.072 MHz STD/MSB PDM stream held at **384,000 bytes/s**, `short=0`, `errors=0`, startup `legacy_rx_q_ovf=5` without subsequent increases.
- With CIC16/FIR17 DSP enabled for >5 minutes, `dsp_drop=0`, `dsp_gap=0`; rare over-budget DSP operations accumulated at ~10 over ~4 minutes, but no dropped blocks; `windows` advanced **3,000 per minute**.
- Bench finger-rubbing readily triggered candidates, but approximately 0.9 candidate/min appeared during one eight-minute nominally unattended indoor trial. A strong ~19.75x signal could not be classified without WAV. Do not interpret candidate number as bat-call or bat-pass count.
- Previously the native MeshCore firmware received and forwarded flood packets at an outdoor hilltop. Local radio range between these particular deployed locations is **not** established.

## Change in FIELD-PILOT-1 (must be validated on device before deployment)

- The DSP now **starts automatically** on *every power-up*, independent of serial/USB host or gateway. The CLI `nzrt dsp off` and `nzrt dsp on` remain available for diagnostics; neither is required in normal operation.
- Each boot generates a random **eight-digit hex session ID**, prints a `NZRT SESSION` line and appends it to the same persisted SPIFFS `/packet_log` read by CLI `log`. Records say `time=UNSYNCED`; there is no dependable absolute time without external time synchronisation.
- Each candidate and five-minute health report contains the session ID and its relative times. `from_ms` / `to_ms` are relative to DSP start **not wall clock**; each `nzrt status` includes `dsp_start_uptime_ms`. Normal boot enables DSP shortly after initialisation, with a small offset between plug-in time and DSP start.
- A reset creates a **new session** and another marker; old logs are deliberately retained across normal USB unplug/replug. `log erase` clears prior observations: never use it before exporting.
- The existing `NZRT ALIVE` ten-second serial heartbeat, `NZRT MIC` minute counters, and saved `NZRT FIELD` / `NZRT BAND` heartbeats remain in place. **This firmware does not retain WAV files** and cannot transmit event summaries over LoRa yet.

## One-time update on user's Windows PC

Use the **existing extracted PlatformIO project** at `$HOME\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor`. Close the USB serial terminal. Fetch and run the branch's helper:

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TheReverendCard/NZRTAudioBatMonitor/exp/meshcore-wildlife-repeater/firmware/meshcore_wildlife/apply_nzrt_detector_update.ps1" -OutFile "$env:TEMP\nzrt-update.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\nzrt-update.ps1"
```

It downloads **four source files**, backs up the previous versions, leaves `platformio.ini`, `platformio.local.ini`, and the private `ADMIN_PASSWORD` untouched, patches the `nzrt dsp on/off` CLI handler if needed, and rebuilds/uploads via PlatformIO on COM8. No ZIP extraction.

## Required unplugged bench pass

1. After successful upload, connect with `py -m serial.tools.miniterm COM8 115200 --eol CR`. Confirm `NZRT SESSION id=... build=NZRT-FIELD-PILOT-1 ... dsp=ON` or `nzrt status` shows DSP on without sending `nzrt dsp on`. Keep LoRa antenna connected.
2. **Close terminal, physically unplug the XIAO, reconnect to a reliable constant 5 V USB supply** (not a low-current auto-off power bank). Record local wall-clock **time and date of plugging in**. Leave 15–30 minutes undisturbed. Avoid touching microphone/cable. If the supply is not a stable mains-backed source, use a different supply.
3. Return to the PC and reattach USB for logging; the device will reboot and log a **new session ID**. Reconnect serial and run `log`, saving its output. Confirm that the earlier, unplugged test `NZRT SESSION` marker and multiple `NZRT FIELD session=...` and `NZRT BAND session=...` lines appear **before** the new boot marker, with `windows` increasing and `dsp_drop`/DMA errors not increasing. Do not mistake the newer PC-powered session for the off-grid session. A sudden power removal can lose up to approximately 10 seconds of unflushed candidate records; markers and five-minute health checkpoints are persisted.
4. If multiple boots occur unexpectedly, logging stops, `windows` stagnates, `dsp_drop` grows, or the supply turns off, **do not deploy**. If it passes, place alongside the SD recorder and reference AR4s with reliable power. Keep mic acoustic port uncovered and weather/splash protection appropriate; no bare electronics outdoors in rain.

## Field trial and analysis

- Record the exact physical **power-on/off wall times** and note any unplugging. Relative log times lack on-device UTC, so matching to AR4/SD observations is approximate and a fresh marker is required after every reboot. A PC time-sync or Wi-Fi RTC feature is a future improvement.
- Co-locate as near as practical to the existing recorders, with comparable open acoustic paths. Do **not** attach to the bat AR4s or alter their power or analysis.
- Two to three nights of candidate counts / timing and hardware-health stability is a sensible pilot if mains-quality power and dry mounting are available. Counts are not comparable species detections without an audio reference; no automatic recording/transfer of WAV in this firmware.
- Retrieve serial `log` and `nzrt status` after the trial and preserve results. `stats-packets` can test opportunistic MeshCore reception, but the wildlife candidates are **not yet transmitted as MeshCore messages**. No hilltop relay installation or transit sign modification is involved.
- `/packet_log` is currently **unbounded**; short pilot only. Longer continuous deployment requires rotation/storage-capacity warning or an alternative bounded journal. High candidate rates could fill SPIFFS.

## Pass/fail for proceeding to classification / LoRa telemetry

A pass requires automatic `dsp=ON` after power-up; durable session marker and health records across power removal; continued capture around 384,000 B/s, `short=0`, `errors=0`, no repeated I2S overflow growth; `dsp_drop` and `dsp_gap` near zero; and `NZRT BAND windows` advancing ~3,000 per minute in undisturbed operation. If these conditions are met we can use the first real-field records to calibrate a more selective two-band pulse-shape gate and then start sending **numbered** events to a private MeshCore house gateway.
