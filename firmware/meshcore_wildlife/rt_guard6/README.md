# GUARD6: qualified RT capture and transfer update

**Installed on the owner's RT and bench-qualified on 19 November 2026 NZDT.** Runtime identity is `NZRT-J6-GUARD-6`. This package contains the exact non-secret `nzrt` sources and receiver extension used for that deployment, including the GUARD5 changes that were not previously in this repository. `source_manifest.json` pins their bytes. The private firmware image, credentials, full-flash backup and original recordings remain on the owner's PC.

## Changes

- Five fixed capture buffers with independent scoring/delivery ownership; no per-recording allocation or flash WAV spool.
- Per-recording retry scheduling, oldest eligible recording first, bounded socket writes, and explicit expiry/discard diagnostics. Wi-Fi association failure does not consume an HTTP retry for every queued clip.
- Exact feature acceleration using symmetric integer FIR and cached FFT twiddles, stage timing, and a low-priority scoring worker on core 1. Microphone acquisition and recovery priorities are preserved.
- Wi-Fi association reuse while work is arriving, with shutdown after 15 idle seconds.
- Optional lossless RTPCM1 transfer packing with capability negotiation and raw PCM fallback. Receiver decoding recreates the original samples and verifies integrity before acknowledgement.
- Receiver dispatch fix for the installed legacy PASS-1 wrapper, preserving SD, RT log, control and model routes. Ordinary and diagnostic RT upload routes are both covered.
- Load probes run from the DSP task every ten seconds and alternate ordinary/diagnostic routes. Equipment-test labels prevent those clips from becoming normal field review data.

Detection thresholds, model weights, 192 kHz mono PCM16, the two-second pre250/post1750 recording policy and the GUARD4 journal/recovery protections are preserved. The classifier remains in shadow mode.

## Hardware evidence

The final image passed four five-minute phases: capture only, upload only, score only, and score plus upload. Each completed **30/30 scheduled captures**, with no busy buffers, acquisition loss or restart. All **61** transmitted WAVs (60 probes plus one natural equipment-test trigger) passed format and integrity checks. Median scoring was **6.54 s** without uploads and **5.47 s** with uploads; median successful transfer was **1.08 s**. Payloads were about **48.7%** of raw PCM size, with no change to saved audio.

Separate temporary HTTP-503 and stalled-transfer tests completed **18/18** captures, scores and acknowledged recordings. The stalled transfer reached the bounded deadline and subsequently succeeded.

The first test at approximately -90 to -94 dBm failed because the queue filled. The antenna was repositioned before the passing tests (roughly -70 to -73 dBm). Both the failure and passing results are retained under `evidence/`; transfer gains cannot be attributed solely to firmware. Finite RAM cannot retain an unlimited backlog on an unavailable or persistently slow link. These are supervised bench tests, not proof of overnight reliability or bat recall.

Normal automatic schedule, evolved detector with assist, inference/WAV enabled, built-in shadow model and test modes off were verified after testing. Boot-lifetime counters retain earlier failures; qualification uses phase differences.

## Rebuild or integrate

Use a **separate copy** of the existing, privately configured GUARD4/GUARD5 MeshCore project. Replace matching files in its `nzrt` directory with this package's `nzrt` files. Preserve the private `WildlifeUploadConfig.h`, `platformio.local.ini`, board configuration, SDK/dependency versions and merge-script fix from that known project. Build the `NZRT_Xiao_S3_WIO_wildlife_repeater` environment. This source overlay is not a complete standalone MeshCore checkout and contains no auto-flashing installer.

The compatible receiver extension is required for packed transfers. Back up the installed extension, use `receiver/receiver_extension.py` with the existing base receiver/configuration, and restart the receiver. Preserve tokens and storage locations. Without the RTPCM1 capability response, firmware falls back to raw PCM. See [transport format](receiver/TRANSPORT.txt).

Before any further flash, preserve pending volatile records, verify board identity and make a same-device rollback backup. A rebuild with other private settings has a different image hash and needs its own qualification; the recorded deployment hash identifies the image actually tested, not a downloadable public binary.

## Reproducible checks

Run `python test_all.py` with a C++17 compiler available as `c++`. In a Visual Studio developer command prompt, use `python test_all.py --compiler cl`. These checks use generated audio and temporary local HTTP servers; they never open a serial device or flash firmware. Set `RT_CODEC_RECORDINGS` to an optional private folder to add up to eight WAV roundtrips. Private WAVs are not required by CI.

The native suite checks feature parity, journal/spool protections, buffer ownership, retry fairness and Wi-Fi reuse. Receiver checks include malformed packed input, original PCM reconstruction, raw/packed RT routes, the installed legacy wrapper interaction, existing 96 kHz SD uploads, authentication, controls and model delivery. Hardware results are recorded separately; host stubs do not emulate microphone, Wi-Fi radio or real flash timing.
