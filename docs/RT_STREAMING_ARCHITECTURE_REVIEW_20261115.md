# RT streaming architecture review

Date:  2026-11-15 NZDT.  Status:  research and proposed experiments only.  Deployed RT remains NZRT-J6-GUARD-4 / JOURNAL-6, downstream builtin-wav-mlp-v01 in shadow.  No firmware, weights, preprocessing schema or promotion settings changed.

## Why reconsider the architecture

GUARD-4 hardware evidence is in [HANDOFF.md](HANDOFF.md).  Its optional clip classifier needs about 11.1–12.2 seconds per two-second clip, while the MLP calculation takes about 54 milliseconds.  The current implementation decimates 192 kHz PCM to 96 kHz, calculates 1024-point FFTs with 512-sample hops, and builds 165 aggregate features using per-clip medians and quantiles.  Its first-pass detector already runs continuously; the expensive downstream classifier is clip-based.  Thus the measured limit is not proof that ESP32-S3 cannot run useful live recognition.

Existing features compress temporal information into band statistics.  Preserving an economical time-frequency sequence could help recognise pulse shape and timing, but that is a hypothesis requiring held-out bat evidence.  Exact whole-clip median normalisation cannot simply be replaced by a running estimate under the same model/schema.  Any changed extractor must be used consistently in training and deployment.

## Distinguish two independent choices

- Streaming inference processes successive chunks, reuses state and returns updated predictions without recomputing an entire overlapping clip.  Training can still occur off-device on recordings; this does not imply online learning or changing weights in the field.
- Raw-waveform learning accepts PCM and learns its own filters/representations.  It avoids an externally specified spectrogram, but the neural frontend still costs operations and memory.
- A streaming recogniser can use either conventional spectral features or a learned waveform frontend.  Neither is inherently the lower-energy option.

Google's streaming KWS framework explicitly supports incremental input and distinct training/deployment graphs [1].  microWakeWord is a practical reference:  16 kHz PCM, 40 spectral values per 10 ms hop and a streaming prediction every 30 ms [2].  Those speech settings are architectural examples, not suitable bat frequency settings or promised bat latency.

## Relevant primary evidence

| Source | Verified result | Limit of applicability |
| --- | --- | --- |
| BioDCASE-Tiny 2026 [3,4] | Ten bird species plus background, three-second recordings at 24 kHz, measured on ESP32-S3-Korvo-2.  MNV2Lite-S1 lists 294.730 ms preprocessing, 361.740 ms model and 664.360 ms total including setup; reported RAM 95,900 bytes. | Different audio rate, classes, preprocessing and firmware workload.  This does not establish ultrasonic performance, continuous operation with our network stack, or weeks of battery life. |
| BirdNET-Tiny Forge [5] | Training/deployment framework actively supports ESP32-S3-Korvo-2. | Explicit early-development status.  Its existing bird models are not NZ bat recognisers or proven all-NZ bird solutions. |
| SincNet bioacoustic study [6] | Demonstrates avian classification directly from raw waveforms with learned band-pass filters. | Supports feasibility of the method, not deployment speed on an ESP32-S3. |
| LEAF and EfficientLEAF [7,8] | Learned audio frontends exist.  EfficientLEAF reports matching LEAF at 3% of its cost on six tasks, while neither consistently beats a fixed mel filterbank. | Learned features are not automatically faster or more accurate; these are not our board/bat benchmarks. |
| ESP-NN and ESP-DSP [9,10] | Official implementations target ESP32-S3 vector instructions and DSP operations. | Check actual operator dispatch, memory placement and numerical behaviour.  Merely exporting an int8 file does not prove an efficient deployment. |
| Embedded Ultrasonics / Esperdyne [11] | Published open-source ESP32-S3 ultrasound monitoring/recording work. | Useful acquisition/heterodyne reference, not evidence of an S3 neural bat classifier. |

## Proposed comparison

1. **Streaming spectral model, first choice to prototype.**  Compute short frames once from the continuous PCM stream, retain a compact feature ring, and feed a causal quantised temporal/depthwise CNN.  Compare fixed linear or bat-focused frequency bands and causal noise normalisation.  Preserve millisecond-scale pulse information; borrow the streaming mechanism from speech work, not its 16 kHz sampling or long speech windows.
2. **Raw-waveform challenger.**  Train a small causal 1-D convolution model or constrained learned filterbank using the same eligible WAV/FLAC recordings and splits.  Bound receptive field, early downsampling, activation RAM and supported operators before large training sweeps.  A BMP has no recoverable waveform phase, so BMP-only AR4/DOC examples cannot become raw-audio inputs.
3. **Cheap streaming pulse-feature baseline.**  Feed existing low-cost pulse statistics into a small classifier, preserving sequence summaries.  It may offer excellent compute cost but can inherit missed cues from the chosen features.  Compare directly rather than presume it has inferior recall.

Use common pass-level recall and false alerts/hour targets, with provenance-aware reviewer weighting and held-out nights/sites/recorders.  AviaNZ candidates and unreviewed periodic clips retain their weak-label status.  Include long background recordings, close passes and realistic start/stop/gap state handling; an event-only dataset selected by the old trigger cannot measure first-pass misses.  Aggregate confidence intervals by independent passes/nights rather than treating neighbouring frames as independent labels.

## Runtime separation

Audio acquisition must keep running independently of model, WAV, journal or radio work.  In the proposed path, incremental features/model state feed an event summariser and bounded report queue.  Optional WAV capture branches from the audio ring and never becomes a prerequisite for a classification.  Stateful models reset or mark uncertain coverage after real sample gaps.  Do not run several expensive challenger models simultaneously on the field board before testing their combined budget.

Retain a sensitive low-cost fallback.  If heavy inference is gated for power, measure the gate's end-to-end recall and include independent audit coverage.  A later classifier cannot recover an event excluded by the gate.

## Power and bird/bat scope

Streaming reduces repeated work but can increase total energy if an expensive model runs all night rather than only on rare events.  Compare energy per listening hour and per detected pass, microphone/decoder baseline, inference duty, and Wi-Fi/LoRa costs using identical workloads.  Weeks on battery remains a whole-device target, not a result established by inference timing.

Speech pipelines at 16 kHz and the BioDCASE 24 kHz dataset cannot retain the ultrasonic band used here.  Keep a validated bat band with anti-alias filtering and sufficient sample rate.  Frequency translation before decimation is a possible later research option, not equivalent to simply lowering the sampling rate.

For the future combined monitor, initially evaluate shared acquisition with separate audible-bird and ultrasonic-bat processing rates/heads.  This allows different time resolution and schedules.  Compare a unified model later; neither all-NZ coverage nor lower power follows from combining classes.  Desktop AviaNZ recognisers can remain separate high-capacity tools and provide labels/teacher predictions with proper provenance.

## Next bounded experiment and gates

Keep GUARD-4 as the monitored field baseline.  Implement a reproducible streaming replay harness plus first spectral and raw-waveform candidates.  Train on the same data, then benchmark board end-to-end processing, worst-case frame latency, activation/work RAM, zero sample loss, burst recall, false alerts/hour and energy.  Make classifier state, preprocessing, band/rate, quantisation and model hashes part of export metadata.

Require processing comfortably within the input-hop budget under acquisition/network load.  Test clip boundaries, state resets, long noise and unknown gaps.  Choose the winner on field-relevant recall and total resource use, then deploy one candidate in shadow.  Existing feature-speed fixes may remain useful for the reference model, but should not commit the project indefinitely to its expensive 165-feature representation.

## Sources

1. https://github.com/google-research/google-research/blob/master/kws_streaming/README.md
2. https://github.com/OHF-Voice/micro-wake-word/blob/main/README.md
3. https://biodcase.github.io/challenge2026/task3
4. https://biodcase.github.io/challenge2026/task3-results
5. https://github.com/birdnet-team/BirdNET-Tiny-Forge
6. https://www.nature.com/articles/s41598-021-95076-6
7. https://arxiv.org/abs/2101.08596
8. https://arxiv.org/abs/2207.05508
9. https://github.com/espressif/esp-nn
10. https://docs.espressif.com/projects/esp-dsp/en/latest/esp32/esp-dsp-library.html
11. https://github.com/raviumadi/Embedded_Ultrasonics
