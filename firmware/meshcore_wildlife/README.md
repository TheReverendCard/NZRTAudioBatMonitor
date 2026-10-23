# Experimental MeshCore wildlife repeater with continuous PDM diagnostics

**Status: early development, not a deployable wildlife detector or trap network.** Built on *genuine* upstream [MeshCore](https://github.com/meshcore-dev/MeshCore) **repeater-v1.18.0**, commit `81dbae592ffad40b4212bc0b37e82b38da08f4bc` (15 October 2026), with a small source overlay in this directory. The upstream MeshCore implementation owns all packet framing, identity, receive, forwarding, routing and radio management. Its MIT licence and upstream copyright remain in force for its code; this repository keeps the overlay separate.

This starts the phase following the successful independent [raw-LoRa OTD v0.2 experiment](https://github.com/TheReverendCard/NZRTAudioBatMonitor/pull/10). It is **not** a MeshCore translation of the transit protocol and must not be flashed onto the running transit gateway/sign.

## What is implemented

- Pinned genuine MeshCore v1.18.0 **Xiao_S3_WIO_repeater** platform and native repeater logic.
- A reproducible `prepare_upstream.py` that overlays a continuous **PDM reader** with 60-second Serial health statistics, initially with no classifier and **no sensor-originated MeshCore messages**.
- Microphone physical wiring unchanged: SPH0641LU4H-1 **CLK D0/GPIO1**, **DATA D1/GPIO2**, 3.3 V, GND, breakout SEL resistor to GND.
- Legacy ESP-IDF4 / Arduino-ESP32 2.x `driver/i2s.h` acquisition for compatibility with MeshCore PlatformIO. Starts at 2.048 MHz BCLK and changes to a 3.072 MHz *target*. The earlier proven v0.1-v0.2 sketch used Arduino-ESP32 3.3.12 and **a different I2S driver**; this port is **not yet validated on the assembled board**, especially actual bitclock and spectral content.
- The internally required but **unwired** WS signal uses **D3/GPIO4**, not D4/GPIO5, because upstream MeshCore assigns D4/D5 to its board I2C bus. Physical WS jumper: **none**.
- PDM reading uses a dedicated FreeRTOS core-1 task, 2,048-byte buffers, bit-density and throughput, partial/read-error counters, and RX DMA event-queue overflow counts; no WAV/SD/Wi-Fi/audio model yet.
- MeshCore runtime powersaving disabled for the bench so capture stays awake, without overwriting the saved settings.
- In the overlay, NZ MeshCore **Narrow** profile **917.375 MHz, SF7, BW62.5, CR4/5** (MeshCore `LORA_CR=5`), with initial 10 dBm TX. This is intentionally **different from the transit gateway's 915 MHz/SF9/BW125/CR4/7**. Test radios must use matching MeshCore settings. See [MeshCore radio presets](https://docs.meshcore.io/radio_presets/); follow NZ [RSM requirements](https://www.rsm.govt.nz/licensing/licensing-in-new-zealand) before any actual RF operation.
- The upstream repeater's insecure default administrative password is replaced with an equally **non-deployable bench placeholder**. It **must** be changed to a unique strong password and the radio/region/privacy configuration reviewed before joining a shared/public MeshCore channel. Startup advertising is disabled for these development builds.

## Reproducible source and build

Install **Git**, **Python 3**, and **PlatformIO Core**. On Windows PowerShell use the Python launcher to avoid requiring `pio.exe` in `PATH`:

```powershell
py -m pip install --user platformio==6.1.18
py -m platformio --version
git clone --branch repeater-v1.18.0 --depth 1 https://github.com/meshcore-dev/MeshCore.git MeshCore-1.18
git clone --branch exp/meshcore-wildlife-repeater https://github.com/TheReverendCard/NZRTAudioBatMonitor.git NZRTAudioBatMonitor-meshcore
py NZRTAudioBatMonitor-meshcore\firmware\meshcore_wildlife\prepare_upstream.py --upstream MeshCore-1.18 --check
py NZRTAudioBatMonitor-meshcore\firmware\meshcore_wildlife\prepare_upstream.py --upstream MeshCore-1.18
py -m platformio run -d MeshCore-1.18 -e NZRT_Xiao_S3_WIO_wildlife_repeater
```

**If `CHECK PASSED` and `PREPARED` already printed:** the overlay succeeded. If PowerShell subsequently reported `pio : The term 'pio' is not recognized`, **do not re-clone or rerun the one-time overlay**. Simply run:

```powershell
py -m pip install --user platformio==6.1.18
py -m platformio --version
py -m platformio run -d MeshCore-1.18 -e NZRT_Xiao_S3_WIO_wildlife_repeater
```

An alternative is the PlatformIO extension inside VS Code, using its own integrated PlatformIO Terminal; an ordinary system PowerShell window will not automatically recognize that environment. The [GitHub Actions reference build](https://github.com/TheReverendCard/NZRTAudioBatMonitor/actions/runs/40012052759) **passed** all steps including compilation of upstream MeshCore + the experimental microphone overlay. It does **not** validate actual mic sampling or packet forwarding on hardware.

**Before flashing to a public MeshCore network:** the generated `MeshCore-1.18/variants/xiao_s3_wio/platformio.ini` currently sets the development repeater's `ADMIN_PASSWORD` to the common placeholder `BENCH_ONLY_CHANGE_ME`. Replace it in the actual `[env:Xiao_S3_WIO_repeater]` block with a **unique, unshared local password (up to 15 single-byte characters)**, then rebuild. Do not commit this credential, place it in an issue/PR, or deploy the placeholder. Never paste private keys or passwords into public logs.

The current NZ community **Narrow** preset uses 917.375 MHz / SF7 / BW62.5 / CR5 with **2-byte path hashes**. The experimental build sets the radio parameters; verify and configure the repeater's path hash mode (`1` for 2-byte hashes; upstream default may be one byte) before treating it as an interoperable community relay. Using the MeshCore serial CLI on the test unit, `set radio.hash_mode 1` is the expected upstream setting (and it is persistent), but verify the response on hardware. A repeater's appearance on an online map is not proof that it is currently on air; last-seen status and actual decoded packets matter.

For a controlled first hardware test, keep the node in serial observation mode and avoid spontaneous advertisements or unnecessary forwarding on a shared network. A trustworthy **A → B → C** forwarding test still requires a genuine source and destination, not just a map pin. The existing transit gateway does not speak MeshCore, so do not expect it to decode these packets.

The script refuses to touch an unexpected upstream revision, overwrite existing `platformio.local.ini`, or apply a patch when a source anchor changed. It changes only the **separate local MeshCore checkout**. It never changes your running transit sign/gateway, the established overnight recorder, or the already-tested raw LoRa sketch.

**Build alone does not validate runtime microphone behaviour or MeshCore routing.** Before flashing, keep a copy of the functioning v0.2 raw bench sketch, attach a suitable antenna, and identify a testable MeshCore network with a real companion and at least one repeater. An actual A → B → C mesh forwarding test requires **three radios**, not just the wildlife board and the raw-LoRa transit USB gateway.

## Hardware and verification gates

1. [x] Working one-way and reverse **raw LoRa** links to OTD gateway; 7+h microphone BCLK/throughput benchmark in PR #10. **This is not MeshCore.**
2. [x] Locate upstream MeshCore 1.18.0 `Xiao_S3_WIO_repeater` environment and native forwarding implementation.
3. [x] Prepare distinct `NZRT_Xiao_S3_WIO_wildlife_repeater` overlay with mic diagnostics and safe pin choice.
4. [ ] **Build** with the pinned upstream PlatformIO toolchain and record flash/RAM usage.
5. [ ] Test this firmware on a spare XIAO/Wio, with a baseline *stock MeshCore repeater* first. Confirm node identity, RF configuration and that a second device can discover it. Do not repurpose the transit sign.
6. [ ] Run 30-60 minute mic + active MeshCore receive/relay stress test; compare read errors, queue overflows, rate, true bit-clock and spectrum against the validated Arduino-ESP32 3.3.12 sampler.
7. [ ] Prove actual A (wildlife) → B (wildlife repeater) → C (companion/gateway) forwarding with original source identity, deduplication and hop/path observed at destination.
8. [ ] Add **sensor-originated** MeshCore native telemetry/event payloads and a decoder. Upstream 1.18 Sensor example has telemetry push, but the stock Repeater does *not* magically implement sensor push. That integration must be deliberate, and trap/site location privacy must be enforced.
9. [ ] Bird/bat/rodent classification and bounded count summaries; optional Wi-Fi clips, with ring buffers, radio airtime and energy accounted for.

**Known differences/risks:** upstream old I2S driver may not match the proven IDF5 PDM bit timing. Event queue overflows are not identical to the newer `on_recv_q_ovf` counter. Radio RF path may generate acoustic EMI; density near 50% doesn't validate actual ultrasonic capture. Continuous capture and all-hours radio listening require an external power plan. We will not merge this as production without on-device and multihop evidence.
