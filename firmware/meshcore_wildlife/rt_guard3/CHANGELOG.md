# Candidate change record

## 2026-11-15:  combined uploader repair, revision 3

Owner supplied the actual upload failure: `Import of non-existent variable 'projenv'`, candidate `merge-bin.py` line 7.  This occurs before the PlatformIO upload action.  The known MeshCore script imports `env, projenv` but never uses `projenv`; PlatformIO's nobuild path does not create it.  Remove only that unused import after exact normalized source-hash verification and a byte-preserving backup.  Unknown script variants stop before serial connection.  New updater records the repair in its deployment receipt and prints upload-log context on subprocess failure.

Combined `NZRT_GUARD3_Upload_Fix_v3.zip` includes the previous CRLF/retry/identity correction.  Apply Upload Fix.cmd accepts either original or serial-repaired tools, backs them up, adds the helper, and preserves existing last_candidate.txt and dependencies.  The candidate merge script is repaired on the next Backup and Upload.cmd run.  No rebuild, firmware-source change, binary replacement, model update, board reset command or board flash occurs while applying the PC-tools repair.

19 Python tests passed, including actual SCons 4.8.1 import-engine reproduction of the same error and successful dry upload-target dispatch after repair with and without a projenv export.  The adapter supplies PlatformIO environment methods; it is not a full PlatformIO/USB run.  Existing binary sentinel remained unchanged.  Covered CRLF preservation, exact backups, repeat/unknown/write-failure cases and prior serial/receiver/workflow tests.  Original-package and serial-patched-package installation tested separately.  Actual Windows USB upload remains pending.  This is the only patch needed by an owner who skipped the serial-only ZIP.

## 2026-11-15:  serial uploader correction, revision 2

Owner reported COM8 identity refusal before upload.  The original uploader sent one LF-only request; the recovered older MeshCore `main.cpp` ignores LF and dispatches on CR.  The successful compare tool already uses CRLF.  This is a reproduced host-tool compatibility defect; the exact owner's failed serial transcript has not been supplied, so a different port or transport issue remains possible if the correction does not resolve it.

Uploader now uses shared CRLF transport with bounded status retries, validates the exact GUARD-2 build and eight-character hexadecimal session, retains boot output, and saves actionable `identity.json` and `before_serial.txt` for success or failure.  DTR/RTS stay false as in the working compare tool.  No automatic port selection, identity bypass, reset command, erase or firmware change.  Full flash backup and source/image hash checks remain mandatory before upload.

Small repair installer backs up the exact original script bytes, accepts only known original/current hashes, preserves the existing build pointer and environment, rolls back completed writes if a later write fails, and supports repeat installation.  Nine added host tests reproduce the LF failure against the CR-only parser, verify both parser styles, delayed/fragmented replies, unknown/heartbeat-only identity rejection, failure diagnostics and no flash invocation, plus installer backup/preservation/rejection/rollback.  Physical Windows USB acceptance remains pending.  Existing compiled candidate can be reused.

## 2026-11-15:  GUARD-3 / JOURNAL-5 preparation

Built from the exact GUARD-2 transform of the five pinned PASS-1 implementation files, plus pinned GUARD headers, RTFeatures and JOURNAL-4.  Input digests are in base_hashes.json.  The owner-local updater also records every copied nzrt source and PlatformIO configuration digest.  No passwords/tokens are bundled.

Implemented independent WAV/scoring ownership, interruptible reference feature extraction, separate persistent inference control, RAM-only journal diagnostics, pressure deferral and repair circuit, receiver status/control additions, source/full-flash backup workflow, and four-phase real-scoring capture load runner with cleanup.  New equipment WAVs and log prefixes are separate from field candidates.  All pre-existing first-pass filters and model weights are unchanged.

Verified host feature parity (990 values), cancellation, lease lifecycle, flash corruption/circuit and recovery, actual transformed ML worker with interface doubles, network retry buffer retention, settings restoration/cancellation, source backup and unknown revision rejection, and authenticated control/ACK dispatch.  ESP32-S3 cross-compiled worker/journal using interface doubles; emulator executed quantile/lease/circuit checks.  Evidence files state scope.  Actual Arduino/PlatformIO whole-project build and microphone/WiFi/flash hardware timing are not verified here.

Pending: owner build/upload and 20-minute loaded test; diagnosis of actual journal failure reason; representative burst/outage hardware validation; frozen real-recording recall comparison; measured ESP-DSP acceleration.  No automatic promotion or field qualification.  No user board was changed by preparing this package.
