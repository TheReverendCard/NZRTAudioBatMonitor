# v0.2 passive Open Transit Display gateway cross-test

**Purpose:** use the owner's *already running* Open Transit Display **v0.8.4a** Museum gateway as a reference receiver/transmitter for two-way raw-LoRa hardware diagnostics, before integrating genuine MeshCore. The current radio firmware is **NOT MeshCore**. No changes are required to the transit Python gateway, USB sender firmware, sign firmware, or its COM-port ownership.

The relevant live OTD v0.8.4a package (20–21 October 2026, available privately to the owner) was inspected. Its sign radio uses `radio.begin(915.0,125.0,9,7,0x12,10,8,1.8)`. Its Python gateway reads received USB serial messages in a dedicated thread and prints them before parsing. Its normal sign HELLO `OTDQ1` and `OTDA2` ACK protocols are unrelated to this probe. **Do not publish or copy the private OTD firmware archive, secrets, or local battery calibration into this repository.**

## Test configuration

| Parameter | v0.2 wildlife XIAO + Wio SX1262 | OTD v0.8.4a |
| --- | --- | --- |
| Frequency | 915.0 MHz | 915.0 MHz |
| Bandwidth | 125 kHz | 125 kHz |
| Spreading factor | SF9 | SF9 |
| Coding rate | 4/7 | 4/7 |
| LoRa sync word | 0x12 | 0x12 |
| Preamble | 8 symbols | 8 symbols |
| TCXO | 1.8 V | 1.8 V |
| Power | 10 dBm | 10 dBm |
| Microphone | D0/GPIO1 CLK, D1/GPIO2 DATA; SEL low | Not attached to USB gateway |

This is a short NZ RF test on a configuration already used by the owner's gateway; operating and legal constraints remain the owner's responsibility. Both radios must have compatible antennas.

## Firmware behaviour

- Microphone raw I2S/MSB acquisition is unchanged, including 2.048 MHz PDM start clock, 3.072 MHz continuous capture, FreeRTOS task and detailed health counters.
- Radio boots into **continuous receive** and reports recognized packet prefix (OTD1, OTD2, OTD3, OTDL1), length, RSSI and SNR, without decoding transit records, sending an ACK, displaying arrivals, or acknowledging packets.
- There is **no automatic transmit** at boot. No repeating and no mesh protocol.
- Serial Monitor at 115200: `s` = health, `p` = **one** short `NZRT1|PING|WILDLIFE|sequence|uptime` probe, `t` = enable/disable legacy 30-second **raw health** packets. For this test, **do not press `t`**. Only use `p` once or twice.
- The gateway's Python reader already logs every incoming serial line, so a successfully received unknown packet should appear in its existing terminal, probably as a bridge `RX_OTHER:NZRT1|PING|...` message. Exact prefix depends on the unchanged USB sender implementation. Gateway intentionally gives **no protocol reply** to NZRT1; a matching received log confirms node -> gateway direction.
- For gateway -> node direction, wait for a **normal scheduled** OTD2 broadcast or an already-occurring sign HELLO/recovery. With overnight quiet enabled, broadcasts may be infrequent. Do **not** force the gateway into `--broadcast-all`, compete for the gateway COM port, or send counterfeit OTDQ1 packets just to speed the test.

## Minimal procedure

1. Save the working v0.1 sketch for rollback. Make sure transit gateway **remains running** with its single existing COM port; do not start another gateway instance or open Serial Monitor on the USB sender.
2. Download the complete **`xiao_wildlife_lora_bringup` sketch folder**, containing both `xiao_wildlife_lora_bringup.ino` **and `WildlifeTypes.h`**, from the experimental branch. Compile/flash only to the *spare wildlife microphone XIAO*, not to the bus sign or its USB LoRa sender. The header is required for Arduino's generated function declarations.
3. Watch for both `MIC started` and `LoRa READY: 915.0MHz ... SF9 CR4/7`. Check the usual 384,000 bytes/s raw PDM rate, ~50% one-density and stable DMA overflow/read counters.
4. Leave the board passive initially. If an ordinary OTD packet passes, the wildlife serial log should show `LORA RX_OK kind=OTD2` or `OTDL1` with RSSI and SNR. No timetable ACK from this wildlife firmware.
5. At a quiet moment, with antennas attached, type `p` into **the wildlife Serial Monitor**, once only. Wildlife prints `LORA TX_OK: NZRT1|PING|...`. Check the **already-running gateway terminal** for a `<- radio:` line containing the same NZRT1 PING packet. This establishes physical over-the-air reception; `TX_OK` alone is not enough.
6. Compare `HEALTH` metrics before and after TX/RX, especially whether `DMAovf` increases. If the gateway does not show it, check physical location, gateway RX state, sender firmware filtering, channel selection, RSSI and radio protocol. Do not edit the live transit gateway to chase the first missing packet.
7. Optionally press `p` a second time, not repeatedly; these are deliberate bench probes on an existing active transit channel.
8. Post both ends' log excerpts on [draft PR #10](https://github.com/TheReverendCard/NZRTAudioBatMonitor/pull/10). Do not claim a tested MeshCore network.

## Rollback / network isolation

If transit ACKs drop, the display behaves differently or radio responses become suspicious, **stop using `p` immediately** and unplug/reflash the *wildlife* test unit. Do not restart or flash the functioning transit sign or gateway as the first response. Returning to v0.1 restores the previous wildlife radio profile, 917 MHz/SF7/4/5, and disables both periodic and MeshCore transmission.

This phase provides an independent direction-by-direction RF link and concurrent audio test. True sensor+repeater **MeshCore** firmware remains a separate planned workstream, and must use upstream MeshCore protocol and roles.
