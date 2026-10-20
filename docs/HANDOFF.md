# Shared development log and handoff

## 2026-10-17:  project baseline

### Agreed direction

The Pixel 6 Pro is the first field platform, using an EMT2 co-located with an AR4.  Process AR4 data through AviaNZ, ideally daily, to build a practical reference dataset.  Use existing and paired data to improve detection, then develop a tiny ESP32-S3 model that initially saves recordings to SD.  Validated activity will eventually feed the Bat Data Collection 2026 workflow.

The primary focus of this workstream is phone software.  Shared interfaces, dataset requirements and hardware dependencies should be recorded here for other contributors.

### Evidence from previous work

These are observations from the prior development conversation, not tests rerun during repository documentation.

- Windows WASAPI exclusive capture succeeded at 256 kHz, mono, 16-bit PCM.
- A subsequent recording showed ultrasonic energy beyond ordinary audio bandwidth.
- The user tested the desktop prototype successfully, including WAV, CSV and JSON output.
- The EMT2 works through the hub in its existing phone app.
- Native capture in our own Android app is unverified.
- The deployment extension and charging transitions remain to be tested.
- Desktop prototype source has not been imported into this repository.

### Completed

Expanded the project README and added the P6P implementation/field plan and shared handoff notes.  No Android app, model integration or hardware validation was completed in this documentation change.

### Work queue

| Priority | Task | Required evidence |
| --- | --- | --- |
| P0 | P6P capture diagnostic | Verified ultrasonic WAV, actual format, input identity and continuity report |
| P0 | USB and charging commissioning | Hardware inventory and extension/charge-transition test results |
| P1 | Background recorder and recovery | Overnight logs, valid files and explicit gaps |
| P1 | Shared event/session schema | Versioned schema and examples for both platforms |
| P1 | Daily AR4/AviaNZ comparison | Reproducible alignment and event matching |
| P2 | Existing data/recogniser inventory | Formats, labels, versions, preprocessing and reuse terms |
| P2 | Tiny-model feasibility | Agreement, memory, latency and power measurements |
| P3 | Aggregate export | Verified destination fields and recorder/model provenance |

### Requests for ESP32 and hardware contributors

- Document exact board, memory/PSRAM, microphone, sampling format and SD interface.
- Keep the capture front end independent of model choice.
- Coordinate preprocessing and event schema changes with phone work.
- Measure sustained end-to-end timing and peak memory including buffers and SD writes.
- Treat ESP32-S3 vector acceleration as CPU instruction support, not separate dedicated AI cores.
- Preserve original audio during early field evaluation.
- Do not assume AR4 spectrogram labels transfer unchanged across microphones and representations.

### Open questions

- Android version/build, hub/switch model, extension length/type and power/data topology?
- Exact AviaNZ version and bat recogniser?
- Which original WAV/annotation pairs are available and under what terms?
- Pass-grouping rule and matching tolerance after inspecting reference timestamps?
- Final aggregation fields, acceptable false-alert burden and uptime limits?

Resolve hardware questions during commissioning and other questions before their respective implementation stages.

## Handoff practice

Read the README, P6P plan, current notes and any applicable repository instructions before working.  Check recent commits/issues to avoid duplicating active work.

For each meaningful change, record the date, focus, linked commit/issue, behaviour changed, test hardware/software and inputs, results, unverified assumptions, cross-platform impact and next action.

Use GitHub issues for actionable requests and link them here.  Keep bulky recordings/datasets, credentials and sensitive site details out of Git.  Use manifests and stable dataset identifiers where appropriate.

## 2026-10-17:  ESP32 workstream onboarding

This conversation workstream focuses on ESP32 firmware, ultrasonic microphone boards, hardware testing/integration and compact model deployment.  The phone workstream and P6P-first field plan remain as described above.

Reviewed the README, P6P plan, shared handoff and recent commits through 813e351.  The repository contains planning documentation and licence only at this baseline; no ESP32 source or hardware results were verified in this review.

Created [ESP32 commissioning issue #1](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/1) to track hardware inventory, reproducible firmware, verified ultrasonic capture, sustained SD recording and cross-platform dependencies.  This update changes documentation only; no firmware was built or tested.

Next action: obtain the current ESP32 capture source, toolchain versions and exact hardware/wiring configuration.  Establish capture timing, signal response and continuity before integrating a model.  EMT2 results are separate evidence and must not be treated as validation of an ESP32 microphone board.

Requests for other contributors: coordinate session/event/health metadata and model preprocessing with this workstream, preserve source audio and label provenance, and flag choices that affect ESP32 memory, sustained processing or SD throughput in issue #1.


## 2026-10-18:  XIAO + SPH0641 ultrasonic capture baseline validated

Validated the microphone acquisition path described in [XIAO ESP32-S3 + SPH0641LU4H-1 ultrasonic capture baseline](XIAO_SPH0641_CAPTURE.md).

Hardware: Seeed Studio XIAO ESP32-S3 with an SPH0641LU4H-1 breakout based on the open-source [meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU) KiCad design.  The assembled board uses a 100 nF decoupling capacitor, R1 = 0 ohm to pull SELECT low, and R2 unpopulated.  The upstream breakout project states an MIT licence and is credited in the dedicated capture document and README.

Two independent tests used simultaneous EMT2 recordings as a reference:

- ESP32 hardware PDM-to-PCM at 64 kHz PCM / 4.096 MHz mic clock reproduced the same approximately 25.7 kHz finger-rub feature as the EMT2, with zero XIAO packet gaps.
- Ordinary I2S/MSB reception used BCLK = 3.072 MHz as a continuous one-bit sampler.  The measured raw stream was 3,068,723 bit/s versus 3,072,000 expected (-0.11%), with 49.997% one-density and zero packet gaps.  Native MSB-first unpacking reproduced the EMT2 approximately 25.7 kHz feature; alternate byte/bit orders did not.

The earlier ESP32-S3 raw-PDM receive experiments produced a persistent approximately 72 kHz framing artefact and are not part of the current design.  The project now uses ordinary I2S/MSB reception for raw PDM acquisition.

Current production direction: 3.072 MHz PDM -> native MSB-first unpacking -> CIC/FIR decimation -> 96 kHz PCM.  Keep 192 kHz as a diagnostic/reference mode until the 96 kHz pipeline is validated.  The 96 kHz target gives a 48 kHz Nyquist limit and is intended to retain the project-relevant pekapeka bands while reducing storage and processing cost.

Next ESP32 actions are no longer basic microphone bring-up.  They are final 32:1 decimation/filter validation, sustained SD capture, outdoor noise/interference testing, power measurement and eventual on-device preprocessing/inference.


## 2026-10-20:  Recorder power roadmap and daytime CPU candidate

Created power feature requests #2–#7, prioritised in [POWER_PLAN.md](POWER_PLAN.md).  The current 5–10 Wh/day energy range is explicitly unmeasured.  Use issue #2 to establish the whole-device 24-hour baseline before selecting a final battery/solar arrangement.

Imported the existing v1.0.1 XIAO overnight pilot into `firmware/xiao_bat_overnight` and prepared a v1.0.2 candidate for issue #3.  It reduces CPU frequency only during safe daytime idle, restores the boot-selected active frequency before NTP/SD/capture, checks readback and defers active work if restoration fails.  The night sampler/DSP, detector and evidence schedule are unchanged.  Existing upstream microphone breakout and capture references are retained.

Host C++ policy tests passed with `g++ -std=c++11 -Wall -Wextra -Werror`.  Added an Arduino ESP32 3.3.12 build check in GitHub Actions; its outcome must be checked before promotion.  No real board was flashed or measured in this work.  USB reconnection, safe collection indication, noon sync, sunset transition, sustained recording and actual Wh savings remain field acceptance gates.  Sleep and hardware power switching stay separate later requests because they affect timekeeping, power-bank compatibility and peripheral sequencing.

Next action: review the candidate PR, check the Arduino build result, then perform a daylight bench test with current measurement before another overnight comparison.  This does not change the P6P implementation or cross-platform annotation policy.
