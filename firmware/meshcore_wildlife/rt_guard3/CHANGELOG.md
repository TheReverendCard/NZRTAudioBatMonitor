# Candidate change record

## 2026-11-15:  serial uploader correction, revision 2

Owner reported COM8 identity refusal before upload.  The original uploader sent one LF-only request; the recovered older MeshCore `main.cpp` ignores LF and dispatches on CR.  The successful compare tool already uses CRLF.  This is a reproduced host-tool compatibility defect; the exact owner's failed serial transcript has not been supplied, so a different port or transport issue remains possible if the correction does not resolve it.

Uploader now uses shared CRLF transport with bounded status retries, validates the exact GUARD-2 build and eight-character hexadecimal session, retains boot output, and saves actionable `identity.json` and `before_serial.txt` for success or failure.  DTR/RTS stay false as in the working compare tool.  No automatic port selection, identity bypass, reset command, erase or firmware change.  Full flash backup and source/image hash checks remain mandatory before upload.

Small repair installer backs up the exact original script bytes, accepts only known original/current hashes, preserves the existing build pointer and environment, rolls back completed writes if a later write fails, and supports repeat installation.  Nine added host tests reproduce the LF failure against the CR-only parser, verify both parser styles, delayed/fragmented replies, unknown/heartbeat-only identity rejection, failure diagnostics and no flash invocation, plus installer backup/preservation/rejection/rollback.  Physical Windows USB acceptance remains pending.  Existing compiled candidate can be reused.

## 2026-11-15:  GUARD-3 / JOURNAL-5 preparation

Built from the exact GUARD-2 transform of the five pinned PASS-1 implementation files, plus pinned GUARD headers, RTFeatures and JOURNAL-4.  Input digests are in base_hashes.json.  The owner-local updater also records every copied nzrt source and PlatformIO configuration digest.  No passwords/tokens are bundled.

Implemented independent WAV/scoring ownership, interruptible reference feature extraction, separate persistent inference control, RAM-only journal diagnostics, pressure deferral and repair circuit, receiver status/control additions, source/full-flash backup workflow, and four-phase real-scoring capture load runner with cleanup.  New equipment WAVs and log prefixes are separate from field candidates.  All pre-existing first-pass filters and model weights are unchanged.

Verified host feature parity (990 values), cancellation, lease lifecycle, flash corruption/circuit and recovery, actual transformed ML worker with interface doubles, network retry buffer retention, settings restoration/cancellation, source backup and unknown revision rejection, and authenticated control/ACK dispatch.  ESP32-S3 cross-compiled worker/journal using interface doubles; emulator executed quantile/lease/circuit checks.  Evidence files state scope.  Actual Arduino/PlatformIO whole-project build and microphone/WiFi/flash hardware timing are not verified here.

Pending: owner build/upload and 20-minute loaded test; diagnosis of actual journal failure reason; representative burst/outage hardware validation; frozen real-recording recall comparison; measured ESP-DSP acceleration.  No automatic promotion or field qualification.  No user board was changed by preparing this package.
