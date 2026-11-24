# MeshCore integration path for the 24-hour wildlife sensor / trap node

Status: **architecture and validation plan, not deployed firmware** (23 October 2026).  Coordination: [Issue #9](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/9).  The current raw RadioLib sketch in this directory is a **bench fixture only**.  It speaks **neither MeshCore nor Meshtastic**, cannot automatically relay other nodes' messages, and is not a MeshCore repeater or sensor.

## Goal

On a single Seeed **XIAO ESP32-S3 + Wio-SX1262**, preserve full-band PDM microphone capture, eventually classify native and introduced birds, NZ bats and candidate rodent calls, send wildlife/trap events across a **real MeshCore network**, and forward eligible MeshCore packets from other deployed wildlife/trap units when practical.

**Current preferences:**  external power and Wi-Fi available; 24-hour audible/ultrasonic listening; no SD; LoRa for small event/health/count summaries; optional short clips to Wi-Fi, never continuous audio over the mesh.  Independently maintain the existing nightly SD/sleep recorder and its firmware branch.

## Critical upstream distinction

MeshCore is a **packet protocol, routing implementation and node-identity/security system**, not merely LoRa PHY settings.  Matching frequency, spreading factor, bandwidth, code rate and sync word does not make the current `NZRT1|H|...` payload compatible.

In stock MeshCore, roles are firmware-defined:

- [Simple Sensor](https://github.com/meshcore-dev/MeshCore/tree/main/examples/simple_sensor): telemetry queries, alerts and custom sensor behaviour.  Sensor telemetry **push** is included in upstream MeshCore [v1.18.0](https://blog.meshcore.io/2026/10/15/release-1-18-0).
- [Simple Repeater](https://github.com/meshcore-dev/MeshCore/tree/main/examples/simple_repeater): forwards eligible mesh packets to extend range; exposes status and selected telemetry.  Stock sensor/companion nodes **do not automatically forward** other nodes' packets.
- A combined **repeater + event-generating wildlife node** needs a custom implementation with actual source-level integration and field validation.  We must not advertise this capability before it has been measured and tested.
- The XIAO ESP32-S3 + Wio-SX1262 combination is supported by [Seeed's MeshCore guide](https://wiki.seeedstudio.com/get_started_with_esp32s3_meshcore/).  Use a pinned upstream MeshCore source release, retain upstream MIT licence/attribution as appropriate, and build custom variants with **PlatformIO** rather than hand-encoding MeshCore packets into Arduino RadioLib.

A backup topology, if the combined workload is not feasible: sensor firmware on selected nodes and separately positioned MeshCore repeater nodes, with a Wi-Fi gateway when available. This would *not* meet the ideal every-sensor-relays preference, so treat it as a testable fallback rather than the current preferred outcome.

## Suggested implementation sequence

1. **Radio compatibility baseline:** use **spare** XIAO/Wio boards to flash the stock MeshCore repeater and companion/receiver using Seeed's official instructions.  Prove that two companions can communicate *through* an intermediate repeater, with matching region/legal RF settings and recorded hop/path information; a direct TX_OK is not proof.  Do not sacrifice an existing field recorder.
2. **Select upstream code:** pin MeshCore version/commit, identify the XIAO S3 WIO platform/variant, initial repeater source, the sensor/telemetry interface and runtime memory, then create a distinctly named `wildlife_meshcore` PlatformIO experiment.  No cloned vendor repository or mixed unreviewed source is required in our main branch initially; document upstream pin and a reproducible patch or fork when real implementation begins.
3. **Integrate microphone:** CLK GPIO1 / D0, DATA GPIO2 / D1, PCB R1 pulls SELECT low, 3.3 V and GND from XIAO. The proven capture mode remains ordinary I2S/MSB sampling with 2.048 MHz startup followed by 3.072 MHz PDM.  Confirm MeshCore GPIOs, SPI, USB, boot, and any I2S dummy WS pin before using GPIO5/D4 in a combined target.
4. **Prove concurrent operation:** high-priority audio sampling plus real MeshCore RX, routing and TX. Report PDM throughput, overflows, read errors, raw-to-PCM spectral evidence, packet forward counts, received SNR, radio airtime, latency, queue/backlog, Wi-Fi interference and memory high-water marks.  Mesh listening must not be silently paused for inference; if a tradeoff is unavoidable, measure and document it.
5. **Native MeshCore telemetry:** first send one unambiguous *test event* and node health information using standard upstream packet/application APIs, not raw strings transmitted at the physical layer. Use a stable source node ID, event ID/sequence, event age/timestamp uncertainty, class/type, confidence/provenance, radio/app version and counters.  Preserve the distinction between **candidate activity** and **confirmed species**.  Test built-in telemetry subscription/queries before deciding whether a custom application payload is necessary.
6. **Gateway delivery:** validate a 3-node chain where node A originates an event, node B (also a sensor) forwards it and a receiving companion/gateway confirms the original source ID, event content and hop count. Verify deduplication, timeouts, retries/ACK assumptions and recovery across power interruptions.  Keep private trap locations and site-sensitive bat locations out of public data.
7. **Application features:** extend from test telemetry to real bird/bat/rodent event summaries, eventually count aggregation (bounded airtime), and optional Wi-Fi clip upload.  Conduct stress and power tests before remote trap use.

## Phase-zero raw LoRa test fixture (PR #10)

The `xiao_wildlife_lora_bringup.ino` sketch can still establish *electrical* microphone/SX1262 coexistence on the same board, with no upstream MeshCore dependency and no SD.  It uses Arduino ESP32 3.3.12 and RadioLib 7.1.2.  **Raw LoRa TX is disabled by default**; enable `t` on a connected serial console ONLY when deliberately testing with a matching custom raw receiver in a legal/configured frequency, with the SX1262 antenna attached.  Such test traffic is *not* forwarded or decoded by MeshCore and must not be used to claim compatibility.

A later real-MeshCore integration should replace **only the raw-radio networking module**, not discard the verified mic configuration or diagnostics. Keep PR #10 draft until its current raw hardware checks are completed, and do not merge it as the production radio stack.

## Coordination and engineering risks

- **Role combination**: a standard Sensor node is not automatically a Repeater; a standard Repeater is not a turnkey originating wildlife detector.  Prefer adapting upstream role logic, or coordinate an integration upstream, rather than writing an incompatible mini-mesh.
- **Prioritisation**: repeater RX duty and microphone sampling both need sustained attention. Single radio is half-duplex; radio TX/forwarding and Wi-Fi can cause RF/electrical noise, and inference can lead to CPU contention. Profile the actual unit, not just free-heap screenshots.
- **Network usage**: plan private application namespace/keys, authentication and a bounded message rate; avoid unnecessary flood traffic on shared public channels.  Adhere to NZ RF regulations and coordinated MeshCore profiles for the chosen network.
- **Licences and compatibility**: preserve upstream MeshCore copyright/notice; do not assume every downstream application/model licence matches our project GPLv3.
- **Power**: this branch assumes steady supply and has its **own** Wh/day budget; battery/solar optimisation is later, and no modifications to the overnight recorder's daytime deep sleep are implied.

References: [Seeed MeshCore for XIAO + Wio](https://wiki.seeedstudio.com/get_started_with_esp32s3_meshcore/), [MeshCore v1.18.0](https://blog.meshcore.io/2026/10/15/release-1-18-0), [MeshCore Sensor Node Intro](https://blog.meshcore.io/2026/09/14/sensor-intro), [MeshCore repository](https://github.com/meshcore-dev/MeshCore), [existing ultrasonic capture](../../docs/XIAO_SPH0641_CAPTURE.md).
