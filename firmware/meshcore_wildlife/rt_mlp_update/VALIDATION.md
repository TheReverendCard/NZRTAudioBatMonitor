# Validation ledger, 6 November 2026

## Source and model provenance

- Recovery baseline: PR #16, commit `d0d30b78a629090e7ca9bf57a12743f5da0c550d`.  The installer verifies the 14 recovered source/configuration hashes against the owner's successful compile receipt before patching.  Later runs verify their previous installed-file hashes.
- WAV MLP host reference: PR #23; original ZIP SHA-256 `5bde7c39ebe56706050769e92a05c30d33a1091a0763ee2b653dc79464f07ad1`.
- This update contains the exact exported float32 scaler/weights, a new bounded extractor and runtime integration.  It does not contain private receiver configuration, MeshCore passwords, user recordings or a device firmware binary.

## Passed locally

1. C++11 host compilation of the bounded feature extractor and numeric model loader.
2. Feature/probability comparison on 17 clips: nine generated clips and eight readable field recordings.  Maximum feature difference from the Python reference: 0.002673805.  Maximum final probability difference: 0.000137999619.  See `tests/feature_results.json`.  Float32 FFT/rounding can change a temporal duty statistic by one frame; this is not bit-exact parity.  These tests establish numerical agreement on these fixtures, not bat recall or precision.
3. The field fixtures were read without WAV truncation warnings.  96kHz recordings were resampled to 192kHz to exercise this RT input contract, then both implementations received the same quantised PCM16.  This does not validate the RT microphone/decimator against Xiao SD.
4. Numeric package loading reproduces all built-in parameters exactly.  Rejected wrong length/schema, nonfinite parameters and invalid scaler.  Nonfinite inference inputs are rejected.
5. Receiver integration tests: RT192kHz WAV wrapping and PCM integrity; SD96kHz route unchanged; both old SD and RT tokens accepted; RT journal route retained; duplicate upload idempotence; bad tokens/checksums/rates/names rejected; staged-model authentication/hash checks; queued-control retrieval/acknowledgement and rejection of unsupported commands.
6. Updater tests against available recovered-source fixtures: valid baseline accepted, repeated installation accepted, changed source refused before mutation.  Python syntax checks passed.
7. New runtime module compiled and linked with the real ESP32-S3 GCC/Arduino SDK, espressif32 6.11.0 and framework 3.20017.241212+sha.dcc1105b.  The standalone SDK harness stubs only the time and standby accessors and does not validate complete MeshCore integration or hardware operation.

## Full firmware build

Full retained MeshCore target **compiled successfully with exit code 0**, including the complete package payload.  Target: `NZRT_Xiao_S3_WIO_wildlife_repeater`.  Static RAM: 107,904 / 327,680 bytes; flash program: 1,274,137 / 3,342,336 bytes.  The additional dynamic PSRAM allocation is approximately 2,262,952 bytes and is not included in that static RAM figure.  `build_receipt.json` records source and binary hashes.  This binary is not distributed because the retained project configuration is private.  The Windows updater builds with the owner's local configuration before flashing.  Full upstream/source identity is not independently locked to the owner checkout; this is not a claim of a bit-reproducible release.

An initial PlatformIO follow-up was blocked by automatic approval review because of possible build/environment telemetry.  PlatformIO telemetry was then explicitly disabled for subsequent local builds and for the Windows updater subprocesses.  No public build logs or firmware binaries are included.

## Not yet verified on the user's device

- Full acoustic capture and feature consistency against concurrent AR4/Xiao SD observations.
- Per-clip inference time, long-run capture gaps, queue pressure, PSRAM stability, power draw and WiFi/MeshCore coexistence.
- Real power interruption during model slot/NVS changes or offline audio uploads.
- Detection accuracy on prospective nights, especially under the two-second RT clip policy.
- Runtime upgrade/download/control behaviour on the actual connected RT and Windows receiver.

The updater's PASS checks identity, journal readback and worker allocation.  The optional `nzrt ml test` checks synthetic features/model execution and reports MCU timing.  Neither substitutes for an overnight shadow comparison.  No device was flashed by this development session.
