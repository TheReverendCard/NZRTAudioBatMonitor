# NZRTAudioBatMonitor

On-device recording and detection of New Zealand pekapeka (bat) activity, starting with a Pixel 6 Pro and Echo Meter Touch 2 and progressing towards a compact ESP32-S3 monitor.

The project will collect original ultrasonic recordings, compare detections with a co-located AR4 processed through AviaNZ, and build a traceable dataset for improving small detection models.  The eventual monitor will aggregate bat activity into the Bat Data Collection 2026 workflow.

## Current status

**Capture prototypes validated; field recorder and classifier still in development.**

Windows EMT2 capture has been verified at 256 kHz, mono, 16-bit PCM through WASAPI exclusive mode.

On 2026-10-18 the ESP32 workstream also established a reproducible ultrasonic capture baseline using a Seeed Studio XIAO ESP32-S3 and SPH0641LU4H-1.  A 64 kHz hardware-PDM-to-PCM test and a separate 3.072 Mbit/s raw one-bit capture both reproduced the same controlled approximately 25.7 kHz ultrasonic feature recorded simultaneously by the EMT2.  The working full-band raw path uses ordinary I2S/MSB receive mode rather than the ESP32-S3 raw-PDM receive format.  See [XIAO ESP32-S3 + SPH0641LU4H-1 capture baseline](docs/XIAO_SPH0641_CAPTURE.md).

The **Pixel 6 Pro remains the first field deployment target**.  Desktop tools support analysis, training and reference comparisons.  Native capture in our own Android app, sustained ESP32 SD recording and bat-classifier performance remain unverified.

## Planned field setup

- Pixel 6 Pro running the future recorder app.
- USB hub/switch arrangement providing microphone connectivity and charging.
- Existing automation enabling charging at 20% battery and disabling it at 80%.
- USB extension to an EMT2 positioned close to an AR4 with comparable orientation.
- AR4 data processed through AviaNZ, ideally daily, as the operational reference.

Document the exact hub/switch, extension and power arrangement during commissioning.  Verify that charging transitions preserve microphone connectivity and USB host operation; log any interruptions and recovery.

## Recording and development workflow

1. Capture native ultrasonic audio into a rolling buffer.
2. Apply a sensitive candidate-activity trigger.
3. Save original WAV clips with configurable pre/post-event audio.
4. Retain scheduled background or continuous audit samples to reveal trigger misses.
5. Save timestamps, capture health, settings and software/model provenance.
6. Match phone events against time-aligned AR4/AviaNZ results.
7. Use existing data and paired recordings to refine detection and build training data.

Candidate ultrasonic activity is not automatically a bat detection.  Preserve this distinction in the interface, metadata and exported totals.

Keep original WAVs as evidence.  Spectrograms can be calculated in memory for recognition.  Compatible BMP export can be added after its format is verified.  Neither a waveform model nor a spectrogram model is assumed best for small hardware without measurement.

## Roadmap

| Stage | Deliverable | Evidence required |
| --- | --- | --- |
| 1. Android capture proof | Short native EMT2 recording on P6P | Ultrasonic content, input identity, sample format and continuity |
| 2. Reliable phone recorder | Background capture, schedule, buffering and evidence files | Screen-off/overnight tests, charging transitions, recovery and storage handling |
| 3. Paired field collection | P6P and AR4 sessions with daily comparisons | Clock alignment, matched/unmatched events and downtime |
| 4. Model development | Existing-data baseline and compact models | Evaluation on held-out nights/sites and versioned preprocessing |
| 5. ESP32-S3 recorder | Local inference and SD event recordings | Measured memory, latency, power and field performance |
| 6. Operational monitoring | Activity aggregation with selected evidence retained | Agreed performance criteria sustained in held-out field sessions |

The provisional “90%+” milestone means capturing at least 90% of AR4/AviaNZ reference passes during overlapping operational periods.  This is reference agreement, not independently verified biological accuracy.  False-alert burden, uptime and event-count agreement must also be assessed.  Phone-only events remain unmatched until investigated.

## Data and models

Use AviaNZ as the initial operational reference.  Identify the exact recogniser/version, preprocessing, weights and decision rules before reuse.  Existing machine-labelled WAVs and available DOC spectrogram datasets may support development after checking annotation quality, formats and usage terms.

Distinguish machine labels, professional review and uncertainty.  Separate training/development and evaluation by recording night or site.  Preserve background and uncertain examples as well as positive candidates.

Design towards streaming processing and compact, potentially quantised models for ESP32-S3.  Benchmark the complete capture, preprocessing, inference and storage workload.  Model file size alone does not establish suitability.

## Optional dual-mode bird and bat monitoring

A proposed second audio stream could identify birds while keeping the validated ultrasonic bat capture pipeline independent.  Options include testing a small bird model on the existing ESP32-S3, an ESP32-P4 or dedicated-NPU companion, a Linux gateway, and delayed/cloud identification.  **This is exploratory only, with no dual-mode firmware validated.**  See [dual-mode bird and bat monitoring options](docs/DUAL_MODE_BIRD_BAT_OPTIONS.md) for the comparison, integration constraints, NZ species scope and acceptance tests.

## Development notes

- [Pixel 6 Pro implementation and field plan](docs/P6P_PLAN.md)
- [XIAO ESP32-S3 + SPH0641LU4H-1 ultrasonic capture baseline](docs/XIAO_SPH0641_CAPTURE.md)
- [Shared development log and cross-platform handoff](docs/HANDOFF.md)

Use GitHub issues for actionable work and these documents for durable decisions.  Record what was tested, the hardware/software used, and what remains unverified.

## Hardware acknowledgements

The SPH0641LU4H-1 breakout used for the ESP32 prototype is based on the open-source [meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU) KiCad design.  The upstream project identifies the board design as MIT licensed.  Credit for that breakout design remains with meerstern and its contributors.

## Licence

See the [GNU General Public License v3.0](LICENSE).  Third-party hardware designs, code, model weights and datasets may have separate terms that must be checked before incorporation.
