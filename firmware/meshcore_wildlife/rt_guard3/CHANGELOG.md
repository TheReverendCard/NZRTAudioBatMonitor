# Candidate change record

## 2026-11-15:  GUARD-3 / JOURNAL-5 preparation

Built from the exact GUARD-2 transform of the five pinned PASS-1 implementation files, plus pinned GUARD headers, RTFeatures and JOURNAL-4.  Input digests are in base_hashes.json.  The owner-local updater also records every copied nzrt source and PlatformIO configuration digest.  No passwords/tokens are bundled.

Implemented independent WAV/scoring ownership, interruptible reference feature extraction, separate persistent inference control, RAM-only journal diagnostics, pressure deferral and repair circuit, receiver status/control additions, source/full-flash backup workflow, and four-phase real-scoring capture load runner with cleanup.  New equipment WAVs and log prefixes are separate from field candidates.  All pre-existing first-pass filters and model weights are unchanged.

Verified host feature parity (990 values), cancellation, lease lifecycle, flash corruption/circuit and recovery, actual transformed ML worker with interface doubles, network retry buffer retention, settings restoration/cancellation, source backup and unknown revision rejection, and authenticated control/ACK dispatch.  ESP32-S3 cross-compiled worker/journal using interface doubles; emulator executed quantile/lease/circuit checks.  Evidence files state scope.  Actual Arduino/PlatformIO whole-project build and microphone/WiFi/flash hardware timing are not verified here.

Pending: owner build/upload and 20-minute loaded test; diagnosis of actual journal failure reason; representative burst/outage hardware validation; frozen real-recording recall comparison; measured ESP-DSP acceleration.  No automatic promotion or field qualification.  No user board was changed by preparing this package.
