# WAV MLP v0.1 portable C++ shadow reference: implementation and status

**Recorded 6 November 2026. State: implemented host-side model and full WAV feature reference; NOT integrated, built or flashed as ESP32 firmware.** This is not a model promotion, firmware release, new field recogniser, or training-data refresh.

## Inputs and immutable provenance
- Owner supplied **WAV MLP** `candidate.joblib`, SHA-256 `497ff930552797bb0d2d43ab701f8ffdfe4960dd8d336e2d73ec039c7913d7c4`, **exactly matched** `report(1).json` from the owner's actual training run. It is not the BMP MLP or CNN.
- Pipeline `StandardScaler -> MLPClassifier`: 165 inputs, 32 and 16 ReLU hidden units, logistic output, class labels 0=noise and 1=bat. Scaler, weights and biases were exported as **float32 C++ arrays** (5,857 weights/biases + 330 scaler parameters, 6,187 floats, 24,748 bytes). Original sklearn fitting arrays were float64. Original validation threshold: `0.9832595196117583`.
- Original feature source `training/phase1/train_baseline_models.py`, SHA-256 `27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923`, currently in the original baseline draft PR #18. Input WAV 96kHz analysis rate, 8–45 kHz 1024-point Hann magnitude spectrogram, 512-sample hop, 192→96kHz default SciPy polyphase filtering when applicable; 32 frequency bands × 5 time summaries + 5 globals.
- Candidate stays experimental. Historical like-for-like test with changed annotations quarantined: WAV MLP TP8, FN1, FP0, TN607 versus original WAV logistic TP8, FN1, FP2, TN605. **Only nine positive cases; no independent current field accuracy claim.** MLP optimiser emitted a non-convergence warning at 300 iterations.
- No original WAV, BMP, `.data`, grades, backups or private credentials were published or altered.

## Source package created

`NZRT_WAV_MLP_Shadow_CPP_Port_v0.1.zip` was generated as a ChatGPT conversation artifact (not committed to repository), SHA-256 `5bde7c39ebe56706050769e92a05c30d33a1091a0763ee2b653dc79464f07ad1`. **The ZIP is the actual source deliverable; this branch only records provenance/implementation state, not the 104 KB generated weights header.**

Files in ZIP:
- `src/wav_mlp_model_parameters.h` actual model+scaler arrays, SHA `f65bc3241cdba3de4855515ce8ac7ec36670248934057437025e28760e2e8e13`.
- `src/wav_mlp_inference.h` portable header-only C++ scorer, SHA `f41806a38a0ad5faa63975d2315e03dd0c0a9c42126c3b59eec98188fc2deec2`.
- `src/wav_features_reference_cpp.h` **host-side** complete 165-feature extractor reference for 96/192kHz mono-equivalent float PCM; SHA `6d26b9becc7b29daeb1e233e951dd26589a2a0a62556dd51d06e6b144aa7083f`.
- `src/export_wav_mlp.py` pinned/checksummed restricted-global owner model exporter, not a general-purpose untrusted pickle loader; SHA `a4adff2fb656c31b28c99230dfe2cfdab54e9d1ba5746997782f607e3d0cb46c`.
- Python/SciPy reference, C++ CLI tools, repeatable host parity tests, Windows batch helper, machine-readable results and README.

## What was verified
Compiled with Linux g++ `-std=c++17 -O2 -Wall -Wextra -pedantic`. Numerical parity using Python sklearn 1.8.0 vs original 1.7.2 fitted model (version warning noted):
- 316 feature vectors (including 4 WAV-derived): C++ scorer max absolute probability discrepancy **6.4562e-8**, 0 non-boundary classification disagreements.
- Eight generated PCM16 mono ultrasonic WAV inputs at 96/192 kHz with durations 0.12, 0.5, 1.5 and 2.0 seconds: complete C++ DSP 165-feature extraction max element absolute difference **9.08971e-6** from source-faithful SciPy reference; final C++ score max probability difference **2.88957e-8**.
- **No real recorder WAV has been cross-checked in this package. No ESP32 compilation, speed, RAM/PSRAM or field testing.**
- The desktop DSP implementation retains an entire intermediate spectrogram (395 bins × frames). For 2-second recording it estimates **1,358,920 bytes** for intermediate and downsampled float data alone, excluding input WAV, stack/allocator/journal/LoRa. At 30s it exceeds typical ESP32-S3 PSRAM. **It is a numerical reference, not a streaming firmware extractor**; don't compile it into the live firmware unchanged.

## Next gates (separate, unmet)
1. Restore source-exact JOURNAL-2 firmware from draft PR #16, including still-missing `WildlifeTime.cpp` and private config, pin all dependencies, compile and capture rollback build identity. **Do not flash older pilot source**.
2. Validate Python vs host C++ on actual independent XiaoRT ultrasonic WAV files. Confirm precise PDM source PCM scaling and recording duration distribution, including saturation, silence and noise.
3. Design memory-bounded streaming/PSRAM feature computation that reproduces all 165 stats and 192→96kHz filtering, compare against host reference and Python across real files. Profile under the existing capture/journal workload. Handle feature calculation failure without touching existing triggers.
4. Run MLP **shadow-only after current RT-SCORE-1 capture**, write model version/SHA, probability, threshold, extract/inference latency, sample-rate, status, source reference, memory stats to non-blocking journal/log; no trigger suppression, OTA, or change to LoRa reporting before tested.
5. Collect new independent reviewed nights with bat positives and diverse negative conditions; freeze a new versioned dataset and compare model error burdens. No auto-retraining from review edits. Preserve grade3/uncertain and ST/mixed exclusions.

See #14 for training eligibility/audit and #22 for model comparisons, #16 for JOURNAL-2 recovery. **Source files from ZIP should be committed as a later distinct change only after an owner/source review; this branch documents their complete current implementation status and hashes.**
