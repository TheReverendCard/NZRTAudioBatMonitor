# Optional dual-mode bird and bat monitoring

Status:  **architecture proposal; no dual-mode firmware or bird model has been implemented or tested.**  
Recorded:  2026-10-22.  
Scope:  Low-cost, solar-friendly monitoring that retains the existing NZ pekapeka ultrasonic workstream and optionally identifies birds locally, at a gateway, or remotely.

## Summary and recommendation

Keep the existing **XIAO ESP32-S3 + SPH0641LU4H-1 ultrasonic path** as the known capture baseline.  Test a second, ordinary-audio microphone and compact bird classifier on the existing ESP32-S3 before buying a new controller.  If inference timing, memory, or simultaneous recording is insufficient, compare an **ESP32-P4 companion/replacement** with a dedicated-NPU option and a small Linux computer.  Keep cloud/gateway identification as a separately selectable mode for installations with connectivity.

A bird-only benchmark is not sufficient:  the accepted design must sustain **ultrasonic capture + audio capture + buffering + inference + SD writing + communications** without losing bat recordings.  No board or model listed below has yet passed that combined test.

## Product architectures we can learn from

| Reference | Compute / identification approach | What it means for this project |
| --- | --- | --- |
| [BirdWeather PUC](https://www.birdweather.com/owners-manual) and its Bat Edition | Captures audio at the device and uploads soundscapes for BirdWeather identification when online.  Offline SD audio can be uploaded and identified later.  Bat Edition exposes birds-only, birds-and-bats and bats-only listening modes. | A low-cost capture/controller board need not execute BirdNET locally if network or delayed upload is acceptable.  **Not evidence of on-device BirdNET performance.** |
| [Terra Station](https://store.terralistens.com/products/terra-station) | Quad-core 1.5 GHz Cortex-A72, 1 GB RAM, 32 GB storage; 48 kHz stereo ADC, local BirdNET 6K analysis; uploads selected FLAC clips and metadata. | Useful full-BirdNET edge-compute reference, but its mains-powered Linux-class design is not a like-for-like solar ESP32 replacement. |
| [BirdNET-Tiny Forge](https://github.com/birdnet-team/BirdNET-Tiny-Forge) | Experimental compact model training/deployment project; **ESP32-S3-Korvo-2 V3.0 is an explicitly supported board**. | First software route to investigate on the existing ESP32-S3; XIAO support, model footprint, microphone integration and concurrency are **unverified**. |
| [BirdNET-STM32](https://birdnet-team.github.io/birdnet-stm32/pretrained-models/) | BirdNET-Tiny global v2.2 Raw bundle offers **1,007 worldwide bird classes** on **STM32N6 NPU** with a 2.5 s / 24 kHz audio input contract. | Demonstrates that a >1,000-class acoustic model can fit a dedicated microcontroller NPU.  It **does not** demonstrate that the same model runs on ESP32-S3 or ESP32-P4. |

The BirdNET-STM32 model's published global benchmark records **0.401 event recall at threshold 0.5** versus **0.545 for a larger BirdNET+ V3 preview** on the same reference data.  These are *recall*, not overall accuracy or precision, and are not Northland-specific results.  Check the current release's model card, region/class coverage, licence and acceptable-use terms before adoption.

## Proposed hardware options

These are capability comparisons, not verified shopping quotes or benchmark results.  Development-board power, battery efficiency and delivered NZ prices must be measured or quoted on the actual units.

| Option | Capability and implementation route | Main limitations | Working position |
| --- | --- | --- | --- |
| **A. Existing Seeed XIAO ESP32-S3** | Add ordinary-audio I2S/PDM microphone; evaluate BirdNET-Tiny Forge or a distilled/quantised NZ classifier while retaining current bat acquisition.  No new main processor. | Finite PSRAM/CPU bandwidth, model operator support, RAM contention, simultaneous audio + SD + LoRa, and practical inference latency unknown. | **Test first.** |
| **B. ESP32-P4 board**, e.g. [DFRobot FireBeetle 2 ESP32-P4](https://www.dfrobot.com/product-2915.html) | Dual-core 360 MHz RISC-V, 32 MB PSRAM and 16 MB flash on this board; extra I2S options; FireBeetle integrates wireless connectivity via a companion chip.  Could act as replacement MCU or companion inference board. | **No dedicated NPU**.  BirdNET-Tiny Forge / STM32 model are **not verified P4 ports**.  Check the chosen board's 5 V consumption, microphone and pin coexistence, and model operator compatibility. | **Next inexpensive board experiment if S3 fails.** |
| **C. Canaan/Banana Pi CanMV-K230D Zero** | Dual-core RISC-V, 128 MB RAM, dedicated KPU neural accelerator, audio interfaces, SD and Wi-Fi.  Potentially more appropriate for larger offline neural networks. | Requires model conversion/operator validation and a different SDK.  No verified BirdNET deployment or combined bat capture here; power remains to be measured. | **NPU alternative to investigate.** |
| **D. STM32N6570-DK / later STM32N6 design** | Official [BirdNET-STM32](https://github.com/birdnet-team/birdnet-stm32) reference deployment for a large Tiny model and dedicated NPU. | Development kit is relatively expensive; a custom production PCB would be later-stage engineering.  Bat PDM stream integration is untested. | **Accuracy/latency feasibility reference; future hardware path.** |
| **E. Raspberry Pi Zero 2 W / Orange Pi Zero 2W / Pi 4-class SBC** | Linux can run established BirdNET tools, handle files/networking and compare with existing BirdNET results; may serve as a local gateway processing multiple sensors. | Higher always-on energy and storage/boot complexity; Zero 2 W has only 512 MB, while Pi 4-class options are a safer starting point for robust continuous local inference. | **Gateway or powered installations, not the first solar edge choice.** |
| **F. Keep sensor ESP32-S3 and process on Wi-Fi gateway/cloud** | The monitor detects and stores/transmits candidates, a home gateway/P6P/computer runs a full bird model, or uploads selected audio for remote classification. | Requires connectivity or delayed processing; raw audio transmission costs bandwidth and energy, particularly over LoRa.  Remote availability/privacy need explicit policies. | **Parallel fallback, not an offline equivalent.** |

**Board-specific published power datum:**  DFRobot lists the FireBeetle ESP32-P4 at approximately **80 mA idle from 5 V (0.4 W, or 9.6 Wh/day if sustained)**, with state-dependent peak current far higher.  This does **not** predict a finished field unit's power, nor bat/bird inference draw.  Measure both active and sleep modes including radio, mic bias, SD and converter losses.  Do not generalise the board datum to all ESP32-P4 designs.

## Audio and dual-mode data path

**Bat path (already demonstrated as a capture prototype):**

1. SPH0641LU4H-1 starts in standard clock mode, then transitions to ultrasonic operation.
2. XIAO uses ordinary I2S/MSB receive to sample PDM at **3.072 Mbit/s**.  The previously tested native raw-PDM receive mode produced a framing artefact and is not the baseline.
3. Decode native MSB-first PDM.  Validate CIC/FIR decimation to **96 kHz PCM** for the proposed operating path, keeping **192 kHz** diagnostics.
4. Run sensitive ultrasonic candidate detection, retain original WAV evidence and background/audit samples, then eventually perform model-based bat identification.
5. Record bat-specific activity and comparisons against co-located AR4/AviaNZ, with missing periods explicit.

**Bird path (not yet implemented):**

1. Add an **independent ordinary-audio microphone**, initially targeting 24 or 48 kHz mono capture as appropriate for the *selected model's exact input contract*.  A low-cost I2S microphone is a candidate, but test outdoor noise floor, acoustic response and electrical coupling first.
2. Use a ring buffer with overlapping model windows and a configurable schedule.  A bird classifier may use spectrogram features or raw waveform depending on the chosen trained model.
3. Run compact INT8 inference on-device where feasible; otherwise send **selected ordinary-audio clips** to a Wi-Fi gateway or store for later analysis.  Do **not** attempt to send continuous PCM over LoRa.
4. Store species, score, input/model/preprocessing versions and representative clips for audit.  Report non-detections only when capture and inference were healthy.

**Shared system:**  Coordinated UTC timestamp, site/device/session IDs, two independent sample-rate and buffer histories, capture gaps, drop counters, storage state, power measurements and optional LoRa **summary events**.  The existing ultrasonic sampling should never be silently downsampled to ordinary bird rates just to share a model.  If pin/clock/DMA resources cannot sustain both paths on one controller, leave the ESP32-S3 in charge of bats and add a companion processor for birds.

A candidate sequence:

```text
Ultrasonic PDM mic -> ESP32-S3 known raw capture -> 96 kHz PCM -> bat trigger/evidence
                                         |
                                         +-> shared timestamp, health, SD, LoRa summary
                                         |
Ordinary-audio mic -> separate capture -> bird windows -> Tiny bird model
                                                or -> optional gateway/full BirdNET
```

## Which NZ birds and how many?

**Class count is not the same as reliable species coverage.**  BirdNET-Tiny's 1,007 worldwide labels should not be called 1,007 supported New Zealand species, and the board itself does not impose a known 30/50/100-species ceiling.

Proposed project *evaluation scopes*, **not proven hardware limits**:

- **30–50 commonly heard birds** at Māra Kokotoha/Northland for initial prototyping.
- **60–100 regional targets** after obtaining reviewed recordings and representative negatives.
- **Broader NZ coverage** only after assessing data balance, confusion, memory, and per-species recall/precision.  Retaining more labels without good local training/validation does not ensure usefulness.

Start with verified species actually recorded at the site, e.g. tūī, korimako, riroriro, pīwakawaka, tauhou, ruru, kōtare, kererū, kākā if present, common introduced birds, and clear nuisance/background classes.  Treat those names as **candidate labels**, not a confirmed species inventory.  Make allowances for multiple simultaneous birds, insect interference, rain/wind, voice, aircraft and unidentified calls.  Restrict geographic priors conservatively so unexpected species are not systematically suppressed.

Benchmark against full BirdNET on a computer/P6P, then review a stratified sample by a person familiar with NZ bird calls.  Full BirdNET output is a **comparison model, not ground truth**.  Blind/held-out **nights and sites** are needed for any reported accuracy.

## Required acceptance tests before selecting production hardware

1. **Bird-model feasibility:**  On the exact target board/model, log binary size, operator compatibility, peak internal RAM and PSRAM, per-window inference time, end-to-end latency and any missed processing deadlines.  Test the correct sample format/window with model configuration and labels versioned together.
2. **Concurrent audio:**  Capture 24+ hours (including dawn and dusk) with both microphones connected.  Log missed PDM samples/packet gaps, audible stream gaps, watchdog resets, CPU load, DMA use and SD write worst-case delays.  Bat stream continuity is the priority.
3. **Detection quality:**  For birds, record per-species precision/recall, false positives per hour and confusion categories against human-reviewed data.  For bats, preserve the existing provisional >=90% agreement target against AR4/AviaNZ during overlapping healthy uptime, with separately reported false-alert burden.
4. **Power:**  Measure idle, bat-only, bird-only, dual-mode active and transmit peaks, plus 24-hour Wh at field duty cycle, including conversion/storage overhead.  Design the solar and battery budget from measured data, not processor datasheet typicals.
5. **Resilience:**  Test power cycling, SD saturation, radio loss, clock drift, rain/noise, microphone faults and recovery.  Neither inference nor radio transfer should block time-critical capture.
6. **Evidence and provenance:**  Save selected original WAVs, uncertain/false-positive examples, scheduled negatives, device and model versions, scores and review flags; set bounded retention and privacy controls.

## Practical implementation order

1. **Keep the bat pipeline intact.**  Do not regress the validated XIAO + SPH0641 raw-I2S acquisition baseline documented in [XIAO_SPH0641_CAPTURE.md](XIAO_SPH0641_CAPTURE.md).
2. **Desktop oracle:**  Run full BirdNET on locally recorded ordinary-audio clips and inventory Northland target labels, missed species and nuisance sounds.
3. **S3 feasibility:**  Inspect [BirdNET-Tiny Forge](https://github.com/birdnet-team/BirdNET-Tiny-Forge) and try its ESP32-S3-supported stack on a compatible development setup; estimate/model conversion effort for the XIAO and measure memory/timing.  First test bird inference separately, then together with ultrasonic capture/SD.
4. **Decision gate:**  If the S3 cannot keep both capture pipelines reliable, test the FireBeetle ESP32-P4 **as a companion** before rewriting the validated bat acquisition.  Compare NPU board and Linux gateway only after measuring their workloads and energy.
5. **Outdoor evaluation:**  Run concurrent sessions alongside the AR4 and, when available, full BirdNET/P6P.  Publish per-model/board evidence and select hardware based on **recall, false-alert burden, uptime, Wh/day and incremental BOM cost**.

## Open decisions

- Is completely offline *bird* identification mandatory for every station, or is gateway/delayed processing acceptable?
- Can ultrasonic and ordinary microphones use separate I2S peripherals/DMA reliably on the chosen board and exact firmware?
- Do we want birds and bats 24/7, or bird-heavy dawn/day and bat-heavy dusk/night schedules **without sacrificing required recording coverage**?
- Which labelled NZ recordings and model licences permit fine-tuning/distribution?
- What incremental BOM and Wh/day ceiling will keep the intended solar/LoRa node viable?

## Sources

- [BirdWeather PUC owner's manual (including Bat Edition modes)](https://www.birdweather.com/owners-manual)
- [Terra Station hardware specifications](https://store.terralistens.com/products/terra-station) and [Terra's bird identification process](https://support.terralistens.com/portal/en/kb/articles/about-terra-s-bird-id)
- [BirdNET-Tiny Forge: supported boards and development status](https://github.com/birdnet-team/BirdNET-Tiny-Forge)
- [BirdNET-STM32: current global Tiny model, benchmark and deployment constraints](https://birdnet-team.github.io/birdnet-stm32/pretrained-models/)
- [DFRobot FireBeetle 2 ESP32-P4: board specifications and power figures](https://www.dfrobot.com/product-2915.html)
- [CanMV-K230D Zero specifications](https://www.kendryte.com/k230_canmv/en/main/userguide/boards/canmv_k230d.html)
- [BirdNET-Pi platform recommendations](https://birdnet.cornell.edu/birdnet-pi/)
- Project's own [ESP32-S3 ultrasonic capture baseline](XIAO_SPH0641_CAPTURE.md)
