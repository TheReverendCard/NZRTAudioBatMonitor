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

The current NZ community **Narrow** preset uses 917.375 MHz / SF7 / BW62.5 / CR5 with **2-byte path hashes**. The experimental build sets the radio parameters; verify and configure the repeater's path hash mode (`1` for 2-byte hashes; upstream default may be one byte) before treating it as an interoperable community relay. The **verified** v1.18.0 MeshCore CLI uses `get path.hash.mode` to inspect this setting and `set path.hash.mode 1` to select two-byte hashes (mode + 1 is the number of bytes). The earlier `set radio.hash_mode 1` instruction was incorrect. Use `get radio` to inspect the stored effective radio profile. The settings are persistent; confirm responses on hardware. A repeater's appearance on an online map is not proof that it is currently on air; last-seen status and actual decoded packets matter.

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

## First on-device serial test (24 October 2026)

Windows firmware upload reported **SUCCESS**, wrote 1,144,368 bytes, flash hash verified. The attached USB serial monitor at COM8, 115200 baud showed:

```text
NZRT MIC t=60s bps=371814 density=49.999% blocks=10893 short=0 errors=0 legacy_rx_q_ovf=5 worstRead=5299us
NZRT MIC t=120s bps=384000 density=50.000% blocks=22143 short=0 errors=0 legacy_rx_q_ovf=5 worstRead=5299us
stats-radio
  -> {"noise_floor":-108,"last_rssi":-113,"last_snr":4.00,"tx_air_secs":0,"rx_air_secs":0}
stats-core
  -> {"battery_mv":0,"uptime_secs":144,"errors":0,"queue_len":0}
neighbors
  -> -none-
NZRT MIC t=180s bps=384000 density=50.000% blocks=33393 short=0 errors=0 legacy_rx_q_ovf=5 worstRead=5299us
```

**Assessment:** the legacy I2S microphone reader runs for at least three minutes with target 384,000 B/s, expected ~50% raw PDM density, zero short or failed reads and just five cumulative startup DMA queue-overflow events (no growth from 60 to 180 s). Native MeshCore CLI is responsive, core error count 0, radio has measured -108 dBm floor. `battery_mv=0` is unsurprising for an unwired/battery-adc-less USB bench. `neighbors -> -none-` and `rx_air_secs=0` at this early point do **not** establish that local MeshCore repeaters are absent or that any authenticated/valid MeshCore packets have been received; **over-air MesCore reception/forwarding remains unverified**. PDM density and bitrate alone are insufficient to establish ultrasonic accuracy or actual bitclock.

### Next passive radio check

These are **read-only** queries accepted by the pinned upstream MeshCore repeater CLI:

```text
get radio
get path.hash.mode
get tx
stats-packets
neighbors
```

Expected stored NZ Narrow radio setting if not overridden by persisted preferences: **917.375, 62.5, 7, 5**. If path hash mode is `0`, issue `set path.hash.mode 1` and check again (mode `1` gives two-byte hashes for *outgoing* packet paths). Do **not** use the incorrect `set radio.hash_mode 1` spelling. Leave device listening for at least 15-30 minutes before interpreting `-none-`; neighbours are mostly learned from advertisements, so packet counters are better for understanding basic reception. Avoid transmitting deliberate `advert` or `discover.neighbors` until administrative password and radio-profile/airtime constraints are verified.

### Extended 23-minute capture and passive reception test

At runtime `t=480` through `1380s`, 60-second PDM health output held precisely at **384,000 B/s**, one-density **50.000%**, `short=0`, `errors=0` and `legacy_rx_q_ovf=5` (unchanged since first report). Maximum observed read latency increased only slightly to **5,320 us**. This establishes sustained mic-driver coexistence with the live MeshCore event loop, not spectral recording fidelity.

MeshCore `stats-packets` counted **`recv=0`** twice during this interval; locally generated sends advanced **3 to 4** (`direct_tx`, no flood TX). `neighbors` remained `-none-`. This is **not yet a successful MeshCore over-the-air receive or forwarding test**. Four sends do not imply four successful links. `set path.hash.mode 1` returned `OK`; this selects 2-byte hashes **for the repeater's own adverts only**, per [MeshCore FAQ](https://docs.meshcore.io/faq/).

The [community New Zealand Narrow radio preset](https://docs.meshcore.io/radio_presets/) (917.375 MHz, SF7, BW62.5, CR5, 2-byte adverts) matches the intended overlay, but nearby map pins may not represent live nodes. A *historical, deprecated* New Zealand profile also used 917.375 MHz but SF11 and BW250. Verify what settings the local repeaters currently use rather than switching presets on the strength of map data alone.

**Next read-only serial commands:** `get radio`, `get path.hash.mode`, `get repeat`, `get advert.interval`, `get flood.advert.interval`, `stats-packets`, `stats-radio`. Check these before an optional **single** `discover.neighbors` request, and only with the unique administrator password configured. The terminal sequences `ESC[3~` and `ESC[C` are keyboard Delete/arrow control codes, not LoRa or I2S errors; avoid using those keys in the simple serial monitor.
