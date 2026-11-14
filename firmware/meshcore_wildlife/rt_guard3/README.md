# GUARD-3 preparation and loaded board test

**Bench candidate.  No physical-board or full owner PlatformIO build is claimed by this package.**  Build identity `NZRT-J5-GUARD-3`; first pass remains PASS-2, journal becomes JOURNAL-5.  This addresses the 15 November GUARD-2 overnight evidence: continuing audio loss, repeated journal quarantine and long downstream feature/scoring latency.  It does not establish that any one subsystem caused those failures.

## Windows sequence

1. Extract to `C:\Users\revje\Documents\Bat\Firmware\GUARD3_Tools`.  Keep the folder together.  Run **Install.cmd** once.  Dependencies live in this tool's own `.venv`.
2. Run **Build Candidate.cmd**.  Select the **GUARD2_Bench_... project actually used for the installed GUARD-2 build**, containing `platformio.ini` and `nzrt`.  The old Downloads patch folder is not a project.  The tool lists generated GUARD-2 projects and also accepts a full path.  It checks all nine pinned source/dependency files before writing anything.  Unknown revisions stop without altering the source.
3. A new private project is created under `Bat\Firmware\GUARD3\<UTC timestamp>`.  The previous project is untouched.  `PreUpdate_Backup\previous_sources.zip` preserves the old nzrt sources and PlatformIO configuration.  `guard3_receipt.json` records the backup, all copied nzrt and configuration hashes and, on success, the compiled image hash.  `guard3_build.log` has compiler output.  **Build does not flash.**
4. When ready for the supervised board test, bring in the RT, connect USB and close Serial Monitors.  Run **Backup and Upload.cmd**.  Select its COM port (normally COM8).  It verifies the running GUARD-2 identity, makes an **8 MB full-flash backup**, checks the backup length and records its SHA-256, then uploads the previously built image without rebuilding.  If identity/backup checks fail it stops before upload.  Keep the project and receipts private: they contain credentials, identity and journal data.  A full-flash backup verifies readable transfer and preserves current bytes; it cannot prove that the old filesystem was healthy.
5. Stop the existing PC receiver and run **Start Receiver.cmd**.  This is an optional wrapper around the installed receiver.  It reuses the existing token and additional tokens and keeps its SD and RT log handlers.  It adds `infer on/off`, `health status`, and separately classified `load_probe` equipment WAVs.  Select the existing receiver.py if asked.  Do not run two receivers on port 8765.
6. Run **Run Loaded Test.cmd** with the RT still on USB and the receiver running.  Default is four five-minute phases plus draining, normally around 20–25 minutes; repeated retries can make it longer.  It uses normal processing and **does not use the old raw bench bypass**.  Return `serial.txt` and `summary.json` from `Bat\Daily_Run_Reports\RT_GUARD3_Load\<timestamp>`.

No new model is promoted or downloaded.  The receiver is never required for the source-only build.  Do not erase journals to run these tests.

## Implemented changes

- Capture publishes immutable PCM to two independent consumers.  HTTP can deliver a complete WAV before scoring finishes.  Only the main loop may recycle the buffer, after **both** delivery and score reporting finish.  Two PCM slots remain; this does not create an unlimited queue.  Expiry, WAV-off and retry exhaustion retire delivery only, never an in-progress reader.
- Downstream inference has an independent persisted `infer` setting, default on when absent.  WAV and first-pass settings stay separate.  Existing saved settings and model are carried through.
- Decimator, FFT and quantile work have cooperative cancellation checkpoints.  Scoring yields periodically and abandons a score if the acquisition backlog reaches half the pool, inference is switched off, or elapsed scoring exceeds 30 seconds.  This is **not** a hard real-time/preemptive limit; a checkpoint can be delayed by another task or flash operation.  A skipped score is `valid=0 decision=fallback_original` with a reason.  The original candidate and any complete WAV remain eligible.
- Feature arithmetic and schema are retained.  Quantile selection is now interruptible; all 165 outputs match the reference exactly on six deterministic full-length fixtures.  The existing portable FFT remains.  **ESP-DSP acceleration and a faster model backend are pending**, not silently substituted.  This candidate may still need further optimisation after hardware timing.
- Logs split total feature/scoring elapsed, feature elapsed, model elapsed, explicit yield waiting and largest observed checkpoint interval.  These are elapsed timers, not pure CPU-cycle accounting.
- Journal repair opens a circuit after three failures in 15 minutes and stops further writer/repair attempts for 15 minutes.  Existing 30-second retry cooldown, reserve space and RAM event buffering remain.  Writes are deferred under audio queue pressure.  Last error reason, first/last uptime, verification length/hash/offset, circuit state and counters can upload from RAM even when the journal cannot be opened.
- Journal diagnostics use a last-verified active-length cache instead of opening every archive on every status call.  `active_verified_bytes` has that limited meaning.  Counts and RAM backlog still have finite retention; reset or an extended outage can lose unconfirmed RAM data.  The circuit prevents a rapid repair loop; it does not diagnose or fix the underlying filesystem defect.

## Commands and remote controls

| Purpose | Serial | Wi-Fi Controls |
|---|---|---|
| Work and RAM journal state | `nzrt health status` | Option 13 |
| Stop/resume downstream MLP computation | `nzrt infer off` / `nzrt infer on` | Option 12 |
| Existing detector settings | `nzrt pass status` | Option 11 |
| Existing WAV switch | `nzrt wav on` / `nzrt wav off` | Options 1/2 |
| End new loaded test and restore settings | `nzrt load stop` | USB runner cleanup / one-hour automatic expiry |

ACKs remain at `WiFi_Backup\RT_Controls\<device>.ack.json`.  Check the new request ID and `accepted_utc`; old ACKs are not current status.  They now include `work` and `journal` fields.  Normal remote polling remains about 30 minutes; bench/first ten minutes poll faster.  No arbitrary remote shell or full firmware OTA is introduced.

## What the loaded test measures

| Phase | Downstream inference | WAV uploads |
|---|---|---|
| load00 | Off | Off |
| load01 | Off | On |
| load10 | On | Off |
| load11 | On | On |

The test temporarily wakes acquisition, sets model output to shadow, and requests a capture every ten seconds through the DSP-owned ring and normal clip/score/upload ownership path.  The ordinary first-pass detector continues running.  Probes use run 0 and high sequence IDs; their logs are `LOAD_ML` / `LOAD_WAV`, and their receiver WAVs go to `RT_Test_Clips`, labelled `equipment_test`, `test_source=load_probe`.  They never become machine-confirmed bats.  Natural events keep normal provenance.

This is a processing/transport load test, **not** a recall test: forcing a capture does not prove that the acoustic trigger recognised a bat.  Test genuine recall separately using reviewed overlapping field recordings or calibrated ultrasonic playback.  Ordinary speakers cannot replay the full ultrasonic band.

Each phase includes pending clip drainage before its ending counters.  It checks acquisition progress, new drops/gaps/DMA/read failures, missing probe results, busy slots, invalid or skipped inference, matched WAV ACKs and new journal errors.  A one-block received/processed boundary difference can be normal; a difference over the 48-block pool is flagged.  A completed run with failed checks is **NEEDS ATTENTION**, not a pass.  Score timing is reported without inventing a speedup threshold.

The runner refuses an already active bench or periodic test.  On completion/cancellation it restores the prior inference, WAV and promotion mode in RAM, and returns to the automatic day/night schedule.  Temporary phase settings are not written to NVS.  USB loss may prevent immediate cleanup; the board's one-hour expiry also restores settings.  On reconnection use `nzrt load stop` if needed.  An intentionally different manual day override is not preserved; run this with the normal automatic schedule.

## Rollback

The original GUARD-2 source project and its firmware are unchanged.  The upload receipt also gives the exact command to restore `flash_before.bin` to the **same RT board** with esptool.  This restores the backed-up firmware, NVS and filesystem bytes, including their previous faults.  Do not restore it to another board or upload it publicly.  Restart the original receiver launcher if rolling back.  GUARD-3's `infer` preference is ignored by GUARD-2; existing model/first-pass/WAV preference keys retain their meanings.

## Verification and limitations

`python test_all.py` runs the emitted C++ feature/lease/worker/journal tests and Python workflow/backup/receiver tests.  Test doubles simulate flash failure and HTTP receipt semantics; they do not emulate flash timing, microphone I2S, RF contention or power loss.  See `evidence/host.json` and, when present, `evidence/s3.json` for measured scope.  Actual full PlatformIO compilation is an owner-side build gate before upload.  A hardware pass is still needed before another field deployment.
