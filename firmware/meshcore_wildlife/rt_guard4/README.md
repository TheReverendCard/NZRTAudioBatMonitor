# GUARD-4: journal isolation and exact feature acceleration

**Candidate for a supervised board test.**  Runtime identity:  `NZRT-J6-GUARD-4`, journal `JOURNAL-6`.  Parent is the exact GUARD-3 source, `NZRT-J5-GUARD-3`.  PASS-2, model weights, microphone pins, sample format and recognition thresholds are preserved.  No physical device was flashed during preparation.  See `evidence/` for the precise validation scope.

## Install and test

1. Extract this complete folder to `C:\Users\revje\Documents\Bat\Firmware\GUARD4_Tools` and run **Install.cmd**.
2. Run **Build Candidate.cmd**.  It first checks the previous GUARD3_Tools `last_candidate.txt`, then the newest project under `Bat\Firmware\GUARD3`.  The expected existing project is `GUARD3\20261114T202342550002Z`.  It verifies all 12 pinned source/dependency files.  Unknown or mixed revisions stop without changing the original.  A specific source can be supplied with `--project "full path"`.
3. The build makes a new private project under `Bat\Firmware\GUARD4\<timestamp>`.  The original project is preserved.  `PreUpdate_Backup\previous_sources.zip` contains the previous nzrt sources, PlatformIO configuration and merge script.  The existing one-line merge-script repair is recognised; the old version is backed up and repaired when needed.  `guard4_receipt.json` records the source/configuration and built binary/ELF hashes.  Build output is in `guard4_build.log`.  **This step does not flash.**
4. Connect the RT, close Serial Monitors, and run **Backup and Upload.cmd**, normally choosing **COM8**.  It verifies the current GUARD-3 identity using the corrected CRLF/retry handshake, saves and hashes an 8 MB full-flash backup, then uploads the already built candidate.  It prints a rollback command for the same board.  Keep these private backups and binaries on your PC because they include configuration and credentials.
5. **Keep the existing GUARD-3 receiver running.**  No token change or receiver replacement is required.  If it was stopped, use its existing `Start Receiver.cmd`.
6. Run **Run Loaded Test.cmd** on COM8.  It checks the new GUARD-4 identity, runs four five-minute inference/WAV combinations with a forced real-audio capture every ten seconds, drains pending work, and restores the previous inference/WAV/model mode and automatic schedule.  Expect around 20–25 minutes, longer with retries.  It records timing automatically; no stopwatch is needed.
7. Return **serial.txt** and **summary.json** from the printed folder under `Bat\Daily_Run_Reports\RT_GUARD4_Load`.  Keep the RT available until the result is reviewed.  “Completed” alone is not a pass, and this test does not measure bat recall.

The test refuses an already active bench/periodic test rather than overriding it.  A one-hour on-device expiry remains.  `nzrt load stop` ends a loaded test if host cleanup fails.  After an unexpected reboot, the runner separately collects the new session's status and attempts to stop test mode.  It leaves the interrupted measurements failed and `settings_restored=false`; any verified post-reboot settings are reported separately.

## What changed

### Journal integrity and capture isolation

- **A concrete file-size bug is removed.**  Arduino-ESP32 2.0.17's new-file `VFSFileImpl` path does not initialise its cached stat structure.  `size()` before the first write can return uninitialised data.  GUARD-3 used that value as its append offset.  GUARD-4 uses the validated existing-file size, or zero for a new file, instead.  This accounts for a possible source of the impossible 1,647,208,303-byte offset in the supplied log.  It does not by itself identify the exact watchdog callsite.
- Validate active file size, append bounds, readback length and historical export lengths before seeking/scanning.  A host fault injection reproduces the observed garbage-size case.
- Every journal `Writer` now commits a complete transaction to a **1 MiB bounded PSRAM queue**.  Queueing is explicitly volatile, not a successful flash write.  A separate 64 KiB plus header staging buffer is used by main-loop writing/export.  No journaling allocation, file operation or network operation is introduced in the audio tasks.
- New journal records, including MLP results and health, can be sent from RAM to the existing authenticated `/rt-log` endpoint.  Only HTTP 200 plus the matching content hash acknowledges that batch.  A failed/mismatched ACK retains it for retry.  Files remain in `WiFi_Backup\RT\<device ID>` using the existing receiver schema.
- ACKed records remain in RAM until verified flash persistence or bounded retention eviction.  Oldest-record eviction distinguishes already-ACKed records from unconfirmed losses.  The queue is finite:  power loss/reboot or a sufficiently long offline period can lose unconfirmed RAM records.  There is no claim of unlimited offline retention.
- A main-loop journal service performs at most one queued transaction per call **only after both capture and DSP have acknowledged stopped**.  Rotation, reserve reclamation and readback occur there.  The gate is closed before waking capture.  Diagnostic storage sizes are cached; an unsampled cache is zero, not proof of an unavailable filesystem.
- A flash write/readback fault **latches further journal writes off for the rest of that boot**.  There is no 15-minute automatic retry, quarantine or active-file deletion after a fault.  RAM enqueueing and Wi-Fi delivery remain available.  Existing archives are not erased to make the test pass.  Ordinary idle rotation retains the existing journal-only retention policy.
- Historical dump/erase requires capture stopped.  An explicit successful `log erase` also clears queued RAM transactions, including any unsent records; it is never called by the updater or test runner.  Journals still use the existing flash format.  The audio journal gate does not claim to intercept all upstream MeshCore flash operations or operator-requested NVS configuration writes.  Those remain separate paths.  Model file downloads now require the same capture-stopped gate.
- Network scheduling reserves an ML/WAV/control turn after at most two report transfers when that work is due, avoiding starvation from repeated RAM reports.  Existing diagnostic capture priority and network timeouts remain.

Useful fields in `nzrt health status` or the receiver command ACK:

| Field | Meaning |
|---|---|
| `ram_ready` | PSRAM queue allocation succeeded |
| `ram_bytes` | Bytes retained locally, including record headers |
| `ram_evicted` | Whole transactions removed to stay within capacity |
| `unconfirmed_lost` | Evicted transactions without a matched receiver ACK or verified flash copy |
| `rejected` | Transactions that could not be enqueued |
| `ram_ack` | Verified RAM upload batches |
| `flash_saved` | Queued transactions persisted and verified in flash |
| `flash_idle` / `flash_ops` | Capture-stopped gate / attempted journal append transactions |
| `latched`, `reason`, `errors` | Flash fault state and cause, distinct from queue acceptance |

The existing Daily importer in the retained Wi-Fi tool sources scans all RT snapshot files, not only the latest text file.  RAM uploads are incremental batches and retain session/run/sequence provenance.  Do not replace that collection with a “latest file only” import.  Owner-local current Daily installation is not changed or independently revalidated by this firmware package.

### Faster, schema-compatible feature extraction

The supplied load10 result spent about 28 seconds in complete scoring, with only about 55 milliseconds in the model.  Feature preparation, scheduling and waiting are the main targets.

- Replace software-double FIR multiply/accumulate work with an **exact Q33 integer dot product**.  All stored float filter coefficients are exact multiples of 2^-33.  The PCM16 product sum is below 2^50, hence exactly representable in the original double accumulator.  Converting the integer result to float and scaling by 2^-48 preserves the original rounded float sample.  No changed filter coefficients, resampling ratio or model feature schema.
- Put the 14,336-byte hot FFT/window/overlap scratch area in **internal RAM**, while the large spectrogram and PCM remain in PSRAM.  Allocation failure leaves the original detector available and reports downstream ML unavailable.
- Adjust the cooperative worker yield interval from 1 ms to 4 ms.  Keep audio-pressure cancellation, the 30-second elapsed deadline, a lower worker priority than DSP, and independent score/WAV buffer leases.  This remains cooperative scheduling, not a hard real-time guarantee.
- A float-only FIR trial was rejected because it changed some pure-tone features.  It is not the shipped implementation.  The selected Q33 path matched all 4,950 feature values across 30 host fixtures, including edge lengths, noise, tones, impulses/bursts and saturated patterns.  See tests for exact fixtures.
- No ESP-NN model replacement, quantised model promotion, ESP-DSP FFT substitution or new sensitivity setting is included.  The speed-up on the actual S3 still needs the loaded hardware test; host/emulator timing cannot establish it.

### Test runner and updater

- Preserve host UTC start/end times and monotonic elapsed time per phase and run.
- Keep the original exception if cleanup also fails.
- Detect session changes, reject mixed-session measurements, and collect post-reset diagnostics separately.  Never call an interrupted run a pass.
- Test checks new audio loss, missing/invalid/busy captures, matched WAV acknowledgements, RAM queue loss/unavailability and flash journal operations during listening.  A latched flash fault is reported as needing attention even if audio/network continued.
- Retain the CRLF identity fix, 45-second status retries, selected-port-only behaviour, hash checks, full-flash backup and known `merge-bin.py` repair.  Old source and private build receipts are preserved.

## Verification and reproduction

Run `python test_all.py` with a C++11 compiler for host feature, spool, journal, worker, upload and Python workflow checks.  Tests include a newly created file returning the observed bogus size, oversized existing files, corrupt/short writes, no flash operations while the gate is closed, latch expiry resistance, RAM wrap/overflow/ACK handling, scoring leases/cancellation, HTTP hash mismatch and ML scheduling fairness.  SCons 4.8.1 is optional for the real import-engine regression.

`python prepare_arduino_probe.py --out <new-folder>` emits a compile/link harness for real Arduino-ESP32 2.0.17 libraries, with explicit Time/Day test doubles and no MeshCore.  Its binary is test-only and must not be flashed.  The actual updater builds against the owner's full source project.

`python prepare_emulator.py` emits an ESP-IDF 5.4.2 ESP32-S3 probe.  Build under `emulator` and run with esp-emu 0.50.0, exit marker `GUARD4_S3_PASS`.  It compares 24,576 actual production FIR outputs, 12 quantile cases and queue/lease/cancellation policies.  Emulator scope does not include this board's microphone, radio, SPIFFS timing, power or bat sensitivity.

The owner build remains a required gate before USB upload.  Test results, compiler versions and integration-build scope are recorded separately in `evidence/`.  No hardware qualification or overnight recall improvement is claimed by preparing this update.

## Source evidence and rollback

- Arduino-ESP32 2.0.17:  [VFS implementation](https://github.com/espressif/arduino-esp32/blob/2.0.17/libraries/FS/src/vfs_api.cpp), constructor/new-file branch and `VFSFileImpl::size()`.
- Espressif IDF 4.4.7:  [SPIFFS limitations](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/storage/spiffs.html).  Filesystem writes/garbage collection do not have real-time bounds.
- Original failure and exact uploaded-file hashes are recorded in the repository's shared handoff.  Exact crash symbolication still needs the owner's matching GUARD-3 ELF.

Rollback uses the exact command printed by `Backup and Upload.cmd` to restore `flash_before.bin` to the **same board**.  This restores the backed-up firmware, settings and old filesystem bytes, including any existing fault.  Do not publish the full backup or private configuration.  Model/WAV settings are not deliberately changed by installing this candidate; the temporary loaded test restores them on a normal completion.
