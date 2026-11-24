# Experimental wildlife LoRa + microphone bring-up (v0.2 OTD cross-test)

**Current v0.2 test:** The wildlife node can passively hear normal Open Transit Display v0.8.4a 915 MHz/SF9/CR4/7 broadcasts and can manually send a short `NZRT1|PING` to its existing USB gateway, **without modifying the transit service**. Follow the complete [OTD_GATEWAY_TEST.md](OTD_GATEWAY_TEST.md) checklist; do not open the gateway COM port twice. The v0.1 radio settings were 917 MHz/SF7/CR4/5 and do not match the bus gateway.

**MeshCore is the network requirement for issue #9.**  This v0.1 sketch is a **raw RadioLib hardware bench fixture, NOT MeshCore-compatible**.  It cannot participate in a mesh or forward other nodes' packets.  Its TX starts **disabled**; use a known matching raw receiver and an appropriate legal RF profile for deliberate testing.  See [MeshCore sensor + repeater integration path](MESHCORE_PLAN.md) for the proposed upstream-based firmware.

**Separate development branch for issue #9.**  This is **not** a replacement for the validated overnight SD recorder or draft PR #8.  It is the first hardware/firmware test for a steady-power, Wi-Fi-available (later), initially SD-free 24-hour wildlife sensor.

## What it does and does not do

- Configures the SPH0641LU4H-1 on **CLK=XIAO D0/GPIO1** and **DATA=XIAO D1/GPIO2**.  SELECT remains tied to ground by the breakout's populated R1; no wire from SEL to D2.
- Uses the **previously documented ordinary-I2S/MSB raw PDM strategy**:  2.048 MHz startup clock, then 3.072 MHz ultrasonic clock.  The dummy I2S WS signal uses GPIO5/D4 **internally only**, with **no wire**.
- Reads continuous raw samples in a high-priority FreeRTOS task and reports raw byte rate, PDM one-density, DMA queue overruns, short reads, read errors and maximum blocking read time.
- Brings up the **Wio-SX1262 via the XIAO B2B connector**.  Can send a test health packet over **raw point-to-point LoRa every 30 seconds**, only **after** explicitly enabling TX by pressing `t` in the serial console.  The first bench test should leave TX off while capturing the microphone baseline.
- **No** WAV files, SD card, Wi-Fi, classifications or bat/bird/rodent detections in v0.1.  PDM one-density near 50% and raw capture throughput are diagnostic checks, **not evidence of correctly captured ultrasonic signals**.  The next milestone is real-audio/FFT evaluation and LoRa receiver confirmation.

## Connections

| Breakout | XIAO ESP32-S3 |
|---|---|
| 3.3 | 3V3 |
| GND | GND |
| CLK | D0 / GPIO1 |
| DATA | D1 / GPIO2 |
| SEL | **Not connected to XIAO**; connected to GND on breakout by R1 |

The acoustic opening is on the breakout PCB's underside.  Keep it unobstructed and facing outward.  Confirm the SEL-to-ground jumper with a meter and inspect for accidental solder bridges or shorts **before** power.  Connect a compatible SX1262 antenna **before radio transmission**.  The radio's SPI and control pins are wired by the B2B board:  SCK=GPIO7, MISO=GPIO8, MOSI=GPIO9, NSS=GPIO41, DIO1=GPIO39, BUSY=GPIO40, RST=GPIO42, RF_SW=GPIO38.

## Flash from Arduino IDE

1. Install Espressif **esp32 board package 3.3.12** and **RadioLib 7.1.2** through the Board Manager and Library Manager.  This prototype uses RadioLib point-to-point, **not Meshtastic or LoRaWAN**.  Flashing it replaces whatever firmware is currently on the selected test board.
2. Open `xiao_wildlife_lora_bringup.ino` in Arduino IDE.  Select **XIAO ESP32S3**, **OPI PSRAM**, 240 MHz CPU, 8 MB flash; enable USB CDC On Boot and use the existing hardware CDC/JTAG USB mode.  Do **not** change the operating, sleep, radio or SD firmware in other branches.
3. The v0.2 test radio defaults to **915.0 MHz, BW 125 kHz, SF9, CR 4/7, sync word 0x12, TX 10 dBm and a 1.8 V TCXO**, matching OTD v0.8.4a.  Choose a lawful NZ frequency and matching receiver settings before transmitting.  The frequency is for this standalone bench protocol only; it may not match an existing transit-display LoRa receiver.
4. With the SX1262 antenna attached, upload to the spare assembled unit.  Open the **115200 baud Serial Monitor** and reset if the beginning of the diagnostic log was missed.  If the port does not appear, confirm Arduino USB CDC settings and the USB cable.  Use BOOT recovery if necessary.
5. Observe `MIC started...`, `LoRa READY...` and `HEALTH...`. **No TX occurs by default.** For the transit gateway check, press `p` once with both antennas attached, then inspect the already-running gateway console. Pressing `t` enables legacy 30-second raw health traffic and is not recommended for this test.  `LORA TX_OK` means the radio accepted a packet, **not** proof of reception or MeshCore compatibility.  Press `t` again to turn raw TX back off.  Type `s` for an immediate health snapshot.  A separate raw-LoRa receiver configured identically is needed to confirm over-the-air delivery.

Typical healthy raw data rate is around **384,000 bytes/s**, with PDM bit density near **50%**.  Neither number alone establishes mic polarity, true acoustic response, bat sensitivity, or absence of all gaps.  `DMAovf`, `readerr` and `short` should remain at zero.  A `HEALTH` line samples lifetime counters; `bps` uses the preceding reporting interval.  A failed radio init should not prevent separate microphone health reporting.

Radio health payload example:

```text
NZRT1|H|0|30|11000|5000|0|0
```

Fields:  protocol, `H` (health, **not detection**), sequence, uptime seconds, total received raw KiB, PDM one-density x100 (e.g. 5000 = 50.00%), DMA overflow count and I2S read error count.  No site coordinates, credentials or recorded animal audio.

## What to report back in issue #9

- Which board/version and Wio-SX1262 module you flashed.
- Boot messages showing mic/radio init status and a 30–60 s sample of `HEALTH` and `LORA TX...` logs.
- A before/during/after comparison with TX disabled and enabled (watch data rate and error counters).
- Any signs of the LoRa module or antenna causing mechanical contact or RF interference.  No microphone or radio must be damaged as part of testing.
- Whether a separate, matched receiver actually saw the transmitted health packet.

## Why this design is separate

This intentionally uses **no deep sleep**, **no SD**, and no Wi-Fi yet.  It is designed to clarify assembly and LoRa/microphone coexistence before TinyML training, band separation, Wi-Fi clips or off-grid power design. **MeshCore support will require integrating genuine MeshCore routing/identity/protocol code, not repurposing this simple radio packet.** The preferred later wildlife firmware will integrate the native MeshCore stack in a custom sensor-plus-repeater build, tested with a 3-node chain. See [MESHCORE_PLAN.md](MESHCORE_PLAN.md). Future fixes should be shared with other repository workstreams only after testing, review and an explicit decision.

References:  [XIAO capture baseline](../../docs/XIAO_SPH0641_CAPTURE.md), [dual-mode options](../../docs/DUAL_MODE_BIRD_BAT_OPTIONS.md), [issue #9](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/9), [Wio-SX1262 hardware](https://wiki.seeedstudio.com/wio_sx1262_with_xiao_esp32s3_kit/), [RadioLib](https://github.com/jgromes/RadioLib).
