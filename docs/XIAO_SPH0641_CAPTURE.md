# XIAO ESP32-S3 + SPH0641LU4H-1 ultrasonic capture baseline

## Status

Validated on 2026-10-18 against a simultaneously recorded Echo Meter Touch 2 (EMT2).

The working ESP32-S3 acquisition path is:

```text
SPH0641LU4H-1
    -> standard-mode startup
    -> 3.072 MHz ultrasonic PDM clock
    -> XIAO ESP32-S3 ordinary I2S/MSB receive mode
    -> continuous 3.072 Mbit/s one-bit PDM stream
    -> native MSB-first unpacking
    -> CIC decimation
    -> PCM
```

The ESP32-S3 native **raw-PDM receive mode is not used** for the current design. During commissioning it introduced a repeatable spectral artefact tied to the driver's 16-bit slot framing. Ordinary I2S/MSB receive mode produced an unambiguous continuous bitstream and matched the EMT2 reference signal.

This document records commissioning evidence, not yet a field-qualified recorder.

## Hardware

- Controller: Seeed Studio XIAO ESP32-S3.
- Microphone: SPH0641LU4H-1 PDM ultrasonic MEMS microphone.
- Breakout: custom-assembled board derived from the open-source [meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU) KiCad breakout design.
- Breakout assembly used for these tests:
  - U1: SPH0641LU4H-1
  - C1: 100 nF
  - R1: 0 ohm, pulling SELECT low
  - R2: unpopulated
- SELECT low means the microphone is the left PDM channel.
- Test wiring:
  - 3.3 V -> XIAO 3V3
  - GND -> XIAO GND
  - CLK -> XIAO D2 / GPIO3
  - DATA -> XIAO D3 / GPIO4

### Breakout-board credit

The breakout PCB used in this project is based on **meerstern/SPH0641LU**, an open-source KiCad converter board that adapts the SPH0641LU4H-1 to a 2.54 mm header and includes selectable pull-up/pull-down configuration for the microphone SELECT pin.

Source: [github.com/meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU)

The upstream repository identifies its design as **MIT licensed**. Credit remains with the original meerstern project and contributors. This repository does not claim authorship of that breakout-board design.

## Relevant microphone behaviour

The SPH0641LU4H-1 has separate standard-performance and ultrasonic clock ranges. The commissioning sequence therefore deliberately starts the microphone at a standard-rate clock before switching to the ultrasonic-rate clock.

A useful external implementation is [AkiyukiOkayasu/pico-PDM](https://github.com/AkiyukiOkayasu/pico-PDM), which contains SPH0641LU4H-specific ultrasonic PDM capture code, performs the standard-to-ultrasonic clock transition explicitly, and uses CIC decimation for PDM-to-PCM conversion. It informed the diagnostic approach used here; code from that repository has not been copied into this repository.

## Test 1: ESP32-S3 hardware PDM-to-PCM proof

Purpose: separate microphone/wiring/clock problems from raw-bit decoding problems.

Configuration:

- ESP32-S3 hardware PDM-to-PCM converter.
- PCM output: 64 kHz, signed 16-bit mono.
- PDM downsample mode: DSR 8S.
- Physical microphone clock: 4.096 MHz.
- EMT2 recorded simultaneously at 256 kHz, signed 16-bit mono through WASAPI exclusive mode.
- Controlled stimulus: finger rubbing near both microphones.

Measured capture:

- EMT2 duration: 10.000 s.
- XIAO payload: 1,280,000 bytes.
- XIAO payload rate: 1,024,000 bit/s.
- XIAO packet gaps: 0.

Strongest 18-31.5 kHz peaks:

- EMT2: approximately 25.695-25.702 kHz.
- XIAO: approximately 25.695-25.706 kHz.

This is a **pass**. The two independent acquisition paths detected the same ultrasonic feature to within a few hertz. This validates the microphone, breakout, wiring, ultrasonic clock transition, ESP32-S3 input path and hardware PDM-to-PCM conversion for the overlapping band.

The broad whole-spectrum correlation metric used during commissioning was not a useful pass/fail metric because the EMT2 and SPH0641 front ends have different gain, filtering, frequency response and directivity. Matching a controlled spectral feature was the decisive evidence.

## Failed path: ESP32-S3 raw-PDM receive mode

Several raw-PDM configurations were tested before the clean path was established.

Symptoms included:

- plausible overall PDM one-density near 50%;
- confusing mono/stereo slot payload rates;
- strong slot-to-slot correlation;
- a persistent, non-acoustic line at exactly about 72 kHz;
- the 72 kHz line survived byte swaps, bit-order reversals and slot-interleaving experiments.

The 72 kHz feature tracked the 16-bit slot/word framing rate rather than the simultaneous EMT2 acoustic signal. The exact same real finger-rub feature around 25.6 kHz could be seen underneath it.

Conclusion: do not use the ESP32-S3 raw-PDM receive format for this project unless its packed slot semantics are independently revalidated. It is unnecessary for the working design.

## Test 2: ordinary I2S/MSB used as a raw one-bit sampler

The successful full-band experiment bypassed raw-PDM mode entirely.

Configuration:

- ESP32-S3 ordinary I2S standard/MSB receive mode.
- I2S frame rate: 96 kHz.
- Two 16-bit slots per frame.
- BCLK: 96,000 x 2 x 16 = **3.072 MHz**.
- The SPH0641 uses BCLK as its PDM clock.
- DATA is sampled continuously as a one-bit stream.
- Raw target rate: **3.072 Mbit/s**.
- Host conversion: native MSB-first bit order, 3-stage CIC, initially decimated 16:1 to 192 kHz PCM.
- EMT2 recorded simultaneously as the independent reference.

Measured capture:

- Expected raw serial rate: 3,072,000 bit/s.
- Measured raw serial rate: 3,068,723 bit/s.
- Error: -0.11%.
- PDM one-density: 49.997%.
- Packet gaps: 0.

The four plausible 16-bit unpacking interpretations were compared automatically. **native MSB-first** was the only interpretation that reproduced the controlled EMT2 feature:

- EMT2 controlled feature: approximately 25.695-25.702 kHz.
- XIAO native-MSB feature: approximately 25.692-25.697 kHz.
- Incorrect bit/byte interpretations produced unrelated peaks spread across approximately 30-65 kHz.

The earlier fixed 72 kHz artefact was absent from the successful ordinary-I2S path.

This establishes the current raw acquisition baseline.

## Production sampling target

A 192 kHz PCM output is useful as a diagnostic/reference mode, but the intended New Zealand pekapeka detector does not need to preserve the microphone's entire nominal ultrasonic bandwidth.

The practical production target is **96 kHz PCM**:

```text
3.072 MHz PDM
    -> CIC/FIR decimation 32:1
    -> 96 kHz PCM
    -> 48 kHz Nyquist
```

This keeps the frequency range of primary interest to the project, including the roughly 28 kHz and 40 kHz pekapeka call regions, while halving PCM bandwidth, storage and downstream processing relative to 192 kHz.

Keep a 192 kHz diagnostic path available until 96 kHz preprocessing and detection performance have been validated against field recordings.

## Current design decisions

1. Keep the microphone startup transition through a standard-rate clock before entering ultrasonic mode.
2. Use ordinary I2S/MSB receive mode as the raw one-bit sampler.
3. Use native MSB-first bit unpacking.
4. Use CIC-based PDM decimation, followed by any required compensation/anti-alias filtering.
5. Target 96 kHz PCM for the production detector; retain 192 kHz as a diagnostic option.
6. Preserve native/raw evidence during development so preprocessing can be re-run.
7. Continue EMT2 and AR4/AviaNZ comparisons as independent references rather than treating any one detector as ground truth.

## Still to validate

- Exact final 32:1 decimation/filter design for 96 kHz production PCM.
- Frequency response and sensitivity of the assembled breakout across the project-relevant band.
- Noise floor outdoors and susceptibility to electrical/environmental interference.
- Sustained recording to SD together with preprocessing/inference.
- Long-run packet/buffer continuity and recovery.
- Power consumption.
- Detection agreement against co-located AR4/AviaNZ data over held-out field nights.

## References and acknowledgements

- [meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU) - open-source SPH0641LU4H-1 breakout/converter PCB used as the basis for this project's assembled microphone board. Upstream README states MIT licence.
- [AkiyukiOkayasu/pico-PDM](https://github.com/AkiyukiOkayasu/pico-PDM) - SPH0641LU4H ultrasonic capture example and CIC-based PDM conversion reference.
- [Espressif ESP-IDF I2S documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/i2s.html) - ESP32-S3 PDM/PCM and standard-I2S peripheral behaviour.
- SPH0641LU4H-1 manufacturer datasheet - operating modes, clock ranges, channel selection and timing requirements.
