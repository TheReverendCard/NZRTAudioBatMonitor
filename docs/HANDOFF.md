# Shared development log and handoff

## 2026-11-15 NZDT:  first GUARD-3 loaded-test log is partial and already exposes faults

Read owner-supplied serial(2).txt, 166,908 bytes, SHA-256 `bdcedbcdefda3e0bba57f3d38a6a237eb84569b9fde7aa51c23fd50769b7ef54`.  Runtime confirms NZRT-J5-GUARD-3 / JOURNAL-5, session 349F773D, evolved assist on, first-pass shadow off, downstream MLP shadow.  Test began at 10:38:01 NZDT; file ends near 10:56:54, about 18m53s later.  load00, load01 and load10 have final counters; load11 has started but has no finish/stop/restoration record.  This is a partial snapshot, not evidence the complete runner failed or stopped.  Ask for final serial.txt and summary.json after the existing run finishes.

Observed first phase (inference off, WAV off): 366 DSP drops, 284 gaps, three journal readback failures, journal operation peak 1,991,045 us; error circuit opened.  Last diagnostic expected_bytes=1,647,208,704 / offset=1,647,208,303 versus observed_bytes=401 is implausible for this filesystem and needs investigation; do not infer a proven root cause or defective hardware.  load01 and load10 show zero new drops/gaps, but journal circuit remained open throughout, so this is not an unconfounded claim that inference/upload causes no loss.  RAM event backlog eventually filled (64), last report ram_dropped_oldest=32; live reporting remained active.  Do not count repeated deferred flash_write_failures as that many new readback-corruption incidents.

load01 has 22 forced-probe score/skip records and 22 matched test-WAV ACK records; probe_busy grew by 7.  load10 has nine completed forced-probe scores, 27.67–28.35 s elapsed each, model portion median ~54.9 ms; probe_busy grew by 21.  Partial load11 has six completed probe scores (26.56–29.65 s elapsed) and seven test-WAV ACKs, including work still scoring.  Elapsed inference includes feature extraction/waits and is not continuous deafness.  No bat labels or recall conclusions from these forced equipment probes.

Status: firmware boot verified and useful hardware evidence obtained, but qualification is not passed and restoration is not established by this file.  Let an ongoing run finish automatically rather than restart it for stopwatch timing.  Keep board available for follow-up after final results; journal correctness/latency and feature throughput remain unresolved.

## 2026-11-15 NZDT:  owner reports successful GUARD-3 USB upload

Owner ran the combined revision-3 uploader on COM8.  Supplied console output confirms the candidate merge-bin.py repair and backup, successful live pre-upload identity check for NZRT-J4-GUARD-2, and a successful PlatformIO upload return.  Private deployment receipt directory is named `20261114T210502091662Z`; it contains deployment.json and flash_before.bin.  Full backup/configuration remains on the owner's PC.  The PC-tool upload blockers are resolved in this reported run.

Deployment state is now **uploaded, awaiting post-boot identity and loaded hardware test**, rather than preparation only.  Do not yet claim zero drops, journal recovery, bat recall or field qualification.  Console output does not provide the new runtime DIAG or a completed loaded-test result.  No new model promotion or overnight validation has been reported.

Next owner steps:  leave RT connected to USB and close serial monitors; stop the previous receiver instance and start the GUARD3 tools' Start Receiver.cmd; run Run Loaded Test.cmd on COM8.  The runner verifies NZRT-J5-GUARD-3, then measures the four inference/WAV phases and restores prior settings plus the automatic schedule.  Expected default duration is around 20–25 minutes, longer if drainage/retries occur.  Return serial.txt and summary.json from the latest Daily_Run_Reports/RT_GUARD3_Load folder.  If it refuses existing bench/periodic activity, inspect the result rather than assuming the test ran.  The previous complete flash backup remains available for same-board rollback.

## 2026-11-15 NZDT:  combined uploader repair v3 for missing projenv

Owner then reached the PlatformIO upload step and supplied `Import of non-existent variable 'projenv'` at candidate `merge-bin.py` line 7.  This log fails before the upload action; the earlier full-flash backup had completed.  The script imports projenv without using it, but PlatformIO's nobuild path does not create that build variable.  Removing only the unused import preserves env and the mergebin custom target.

Implemented a hash-checked, byte-preserving backup and one-line candidate merge-script repair in `merge_upload_fix.py`, called by the updater after source/image checks and before serial connection.  Unknown scripts stop untouched; already-repaired scripts are accepted.  Repair receipt is included in deployment.json.  Upload subprocess failures now record upload_failed and print the final 40 upload.log lines.  Firmware code, model, source pinning, compiled binary and build receipt are unchanged by this repair; no rebuild needed.

**One combined patch only:** [NZRT_GUARD3_Upload_Fix_v3.zip](../releases/rt/NZRT_GUARD3_Upload_Fix_v3.zip), SHA-256 `4c9e5a63fb86c3d2d01fdb3682f989610f1d79ee8c16c22d793ae59a9f87c64d` (21,809 bytes).  Includes the CRLF/retry/identity repair and accepts original or serial-only-patched tools.  Extract to a new folder, run Apply Upload Fix.cmd against existing GUARD3_Tools, then run its Backup and Upload.cmd on COM8.  Installer backs up PC scripts and adds the helper; next upload invocation backs up/repairs the candidate merge script.  Existing last_candidate.txt, environment and private compiled candidate are retained.  Full [preparation ZIP](../releases/rt/NZRT_GUARD3_Prep.zip) updated to revision 3, SHA-256 `bd6a5d6b9ea9cb5b60d4e65f542e54a31773d8df394c1f8f623260780ad689f6` (164,639 bytes).

Verification:  19 Python host tests, including actual SCons 4.8.1 Import-engine reproduction and dry upload-target dispatch after repair with and without a projenv export; PlatformIO-specific environment methods were adapted, so this is not a full PlatformIO/USB integration test.  Tests preserve binary sentinel, exact LF/CRLF backups, repeat/unknown/write-failure behaviour, plus existing serial/receiver/workflow checks.  Combined repair installed against both actual original and serial-patched ZIPs, preserving the build pointer.  Original firmware-source and new ZIP hashes verified.  Evidence in evidence/upload_fix_v3.json.  Actual owner USB retry and loaded-test qualification remain pending.  No board flashed here.

## 2026-11-15 NZDT:  GUARD-3 uploader serial compatibility fix, package revision 2

Owner reached COM8 upload preflight and got `GUARD-2 identity not confirmed; nothing uploaded`.  The shipped uploader sent one LF-only status command.  Recovered older MeshCore main.cpp ignores LF and dispatches on CR; the successful compare tool already used CRLF.  Host regression reproduces that failure.  The owner's failed transcript is not available, so identity/port/transport should still be checked if the correction does not resolve it.

Updated `serial_link.py` and `upload_candidate.py` to send CRLF, retry read-only status for up to 45 seconds, require an exact live GUARD-2 DIAG and complete session ID, preserve boot output, and write `before_serial.txt` plus `identity.json` on failure/success.  Selected COM port only; existing DTR/RTS false retained.  Unknown firmware, heartbeat-only and no-output cases stop before backup/upload.  Source/image checks and the full 8 MB flash backup remain required.

[Small repair ZIP](../releases/rt/NZRT_GUARD3_Serial_Fix.zip), SHA-256 `be9a40225092188e18c4db9ec15b0499bc6f648216295c8058c52cbf76eaaec0` (19,726 bytes).  Extract and run Apply Serial Fix.cmd against the existing tools folder, then rerun Backup and Upload.cmd on COM8.  The installer verifies known old/current script hashes, backs up exact bytes, rolls back completed writes on failure, and preserves last_candidate.txt, dependencies and the private compiled project.  No rebuild needed.  [Complete preparation ZIP](../releases/rt/NZRT_GUARD3_Prep.zip) replaced with corrected revision 2, SHA-256 `a4359cebccdac8973571f730ce85b20fd464d263423b1830932c85113d6cb929` (156,899 bytes).  Original source pinning, firmware implementation, weights, generated build identity and emulator evidence are unchanged.

Validation:  14 Python host tests pass, including nine new serial/installer regressions for CR-only and CR/LF dispatch, delayed/fragmented replies, rejection, failure receipts, no flash-tool invocation on identity failure, backup/repeat/version rejection/rollback.  Repair installation against the actual original ZIP passed.  Firmware/source hashes compared against original package and ZIP contents verified.  Real Windows USB backup/upload and hardware qualification remain pending; no board flashed here.  If the owner's retry fails, inspect the newly printed identity.json and before_serial.txt, not the private full-flash image.

## 2026-11-15 NZDT:  GUARD-3 source and loaded-test package prepared, not installed

[Download package](../releases/rt/NZRT_GUARD3_Prep.zip) · [source, Windows workflow, controls and rollback](../firmware/meshcore_wildlife/rt_guard3/README.md) · [change record](../firmware/meshcore_wildlife/rt_guard3/CHANGELOG.md).  ZIP SHA-256 `41104eec7789b774d5ef8f9524e5e39d61a8cb21d525b2f58259f6fd41e9b356` (147,128 bytes).  Based on GUARD-2 source, not an unseen owner source folder.  Identity NZRT-J5-GUARD-3, JOURNAL-5; PASS-2, recogniser weights and first-pass policies preserved.

Implemented independent immutable-PCM score/delivery leases, persisted inference enable/disable separate from WAV, cooperative feature/FFT/quantile cancellation under half-pool audio pressure or a 30-second elapsed deadline, explicit skipped-score fallback, split timing, journal error circuit (three failures in 15 minutes -> 15-minute suspension), queue-pressure write deferral and RAM-only error diagnostics included in live WiFi health/control ACK.  Two buffers remain; sharing does not imply unlimited capacity or a hard scheduling bound.  Feature arithmetic is unchanged; ESP-DSP/INT8 acceleration remains future work.  Added optional receiver wrapper and authenticated infer/health controls without replacing SD/RT log endpoints or tokens.

Windows tooling creates a new Bat/Firmware/GUARD3 project, checks nine exact implementation/dependency hashes, preserves the original source project and a ZIP of previous sources/config, builds without flashing, and records all nzrt/config/image hashes.  Separate explicit uploader verifies GUARD-2 identity and backs up full 8 MB flash before a no-rebuild upload.  Full-flash transfer is size/hash checked, not proof that its filesystem was healthy; backup contains secrets and belongs only on the owner's PC.  Rollback command is printed for the same board.

Loaded runner temporarily forces normal acquisition with raw-bench bypass OFF, requests real microphone-ring captures every 10 s, and compares four 5-minute inference/WAV off/on phases including drainage.  Probe logs/WAVs are marked equipment tests; natural detections keep their own provenance.  Checks drop/gap/read/DMA deltas, progress, journal errors, missing/busy/invalid probes and matching upload receipts.  Restores prior inference/WAV/promotion mode and automatic schedule on exit; one-hour on-board expiry handles host loss.  It refuses an existing bench/periodic test.  Quiet forced-capture success is not bat recall; separate reviewed waveform/ultrasonic testing still required.

Verification: host exact feature parity 990 values across six full-length deterministic inputs; cancellation, lease completion orders, actual transformed worker with interface doubles, pressure fallback and inference-off/WAV-on, incomplete capture, network retry retention, deadline, settings restoration; corrupt-write circuit/pressure deferral/RAM reporting/recovery; five Python tests covering four-phase results, missing counters, cancellation cleanup, existing bench preservation, backup/version rejection, authenticated controls and ACK content.  ESP32-S3 cross-compilation of worker and journal with test interfaces; esp-emu 0.50.0 ran 12 quantile parity checks plus cancellation/lease/circuit-wrap tests using IDF 5.4.2 runtime.  Evidence is scoped in `evidence/host.json` and `evidence/s3.json`.

**Not yet verified:** full owner Arduino/PlatformIO build, actual USB backup/upload workflow, actual receiver wrapper installation, I2S/flash/RF timing or overnight sensitivity.  No board, NVS, receiver installation, model, original recordings or Daily Run files were changed by preparing this candidate.  Next: owner builds first, then brings RT to USB for backup/upload and the loaded test with receiver running.  Return serial.txt/summary.json.  Do not treat existing GUARD-2 quiet-test results as qualification for this image, auto-promote a model, or erase data to get a passing result.

## 2026-11-15 NZDT:  recommended next RT update, proposal only

Proposed next candidate scope: protect capture under real event load, decouple WAV delivery from downstream scoring, and bound repeated journal repair.  This is a recommendation, not an implemented GUARD-3 release or a deployment decision.  Current device remains GUARD-2.  No receiver command, model or settings were changed.

Source review of retained RTFeatures.h and pinned WildlifeML.cpp: clip states currently pass READY -> SCORING -> RESULT -> UPLOAD; two clip slots.  Thus upload of a captured candidate waits for downstream feature extraction/scoring, which took 18.7–22.0 seconds elapsed in the supplied overnight valid results.  Worker is already lower priority (core 0, priority 1), and already yields per FFT frame/band.  Lowering priority or adding an arbitrary delay is not a demonstrated cure.  RTFeatures uses a portable 1024-point FFT, double accumulation in the decimator/statistics, and a large PSRAM spectrogram workspace; overlap caching already exists.  Timer wraps feature extraction, model evaluation and waits, so separate those measurements before assigning cost to the MLP itself.  The builder pins five implementation files but copies feature/journal dependencies from the owner's project; next updater must include those dependency hashes/provenance.

1. Add independent remote downstream-inference enable/disable and status, preserving WAV capture/upload and the selected first-pass detector.  Existing first-pass shadow off and wav off do not disable MLP computation.  No current command syntax is promised for the new control.
2. Make inference resumable in bounded pieces with queue-pressure and elapsed-budget checks.  Protect the reader/DSP first.  Defer or explicitly skip an auxiliary score when necessary, never label the skipped clip negative or suppress its original candidate.  Permit eligible WAV delivery independently of scoring with explicit buffer ownership/refcounts so no buffer can be recycled while either task uses it.  Merely running both consumers concurrently does not free a buffer sooner than the last consumer and adds contention; bound work and benchmark it.
3. Journal already has a 30-second failure cooldown, reserved space and a RAM event backlog.  Extend this with a circuit breaker for repeated repair/quarantine and RAM diagnostics for reason, offset/expected-versus-read checksum/length, first/last failure times and retry counts.  Carry that compact diagnostic in WiFi health independently of successful flash logging.  Preserve bounded event reporting during storage failure and explicitly report overflow/reset-loss risk.  Do not claim underlying flash damage or erase/format the device from these counters.
4. Accelerate measured feature hotspots using a compatible, pinned ESP-DSP backend (official S3 optimized FFT/FIR support), precomputed tables and carefully verified arithmetic changes.  Keep a portable reference and compare all 165 features and final decisions on frozen positive/negative/gap test clips before replacing the deployed extractor.  Do not claim an arbitrary speedup or that an INT8 NN export accelerates its preceding signal processing.  Changing features materially requires versioning/retraining, not silently reusing old weights.
5. Replace quiet-only qualification with normal-path repeated-trigger replay/bench: fixed detector, downstream inference independently off/on, WAV independently off/on; representative burst loads and receiver outages; journal repair fault injection.  Record real acquisition drop/gap deltas, queue occupancy, scoring compute/wait times, clip skips, linked uploads and recovery.  Existing compare mode bypasses ordinary candidate inference and cannot qualify it.  Emulation validates logic/parity; actual board measurements decide timing.  No zero-loss claim until the representative load test passes.

Reference for planned acceleration: https://github.com/espressif/esp-dsp and https://docs.espressif.com/projects/esp-dsp/en/latest/esp32/esp-dsp-benchmarks.html.  Next evidence needed for journal root cause: earlier receiver snapshots preceding the retained 02:56 health records, or new independent error diagnostics; current snapshot already establishes ongoing audio loss so another unchanged overnight is not required to justify this work.

## 2026-11-15 NZDT:  GUARD-2 overnight WiFi snapshot confirms deployment but continued loss

Owner supplied receiver snapshot `1794681621_8c58c7114179d526.txt` and matching JSON.  Verified 192,878 bytes and SHA-256 `8c58c7114179d52648ddacda55268367196cb5cb0c04c92f5abae28fe2dfd2e6`.  Snapshot UTC 1794681621 = 15 November 07:40:21 NZDT.  Receipt firmware NZRT-J4-GUARD-2; retained records session 966D3E85, run 2.  Current first pass PASS-2 evolved assist, first-pass shadow off; built-in WAV MLP shadow; WAV on.  All 108 retained candidate records have bench=0.  Scheduled standby at 06:39:19 NZDT.  Old controls ACK shown by owner is 13 November 07:00:45 UTC, PASS-1 legacy/off, and is stale, not evidence of rollback.  Menu 11 -> status requests a new first-pass response without changing policy; compare request ID and accepted_utc in RT_Controls/<device>.ack.json.

**Overnight trial did not meet uninterrupted-audio or journal reliability criteria.**  Final cumulative since-boot microphone counters: 16,993 DSP blocks dropped, 12,491 stream gaps, 52,168 DSP over-budget blocks.  Short reads/read errors zero; RX queue overflow remains five throughout retained FIELD samples.  From first detailed FIELD at 02:56:37 to daytime standby, drops rise from 15,369 to 16,993 (+1,624) and gaps from 11,312 to 12,491 (+1,179).  Microphone blocks/windows progress; 120 retained live-health lines report MONITORING (55) or GAPS (65), guard_online=1, guard_fault=0, previous_fault=0 and safe=0.  No sustained stopped detector or reboot is visible in this retained portion.  Guard stall protection does not make recurring data loss acceptable.  Missing block payload is ~90.63 s since boot (~8.66 s in the detailed retained interval); this excludes filter/history settling and does not count missed bats.

JOURNAL-4 reports errors=375 and quarantined=375 already at segment start and first retained status, unchanged through the last sample.  Verified writes advance 210 -> 586; latest fault/read_fault=0, active_discarded=0.  Retention discard counter 375 -> 376, deferred retries=824.  This is recovery after substantial earlier journal trouble, not an error-free night.  Underlying failure reason and earlier event/health history are not in this snapshot; retrieve earlier receiver snapshots if available.  Receipt complete=true means the transferred payload validated, not that the full night's journal survived.

Final since-boot counters: 134 candidates (29 RT-SCORE-1 bat_like, 105 uncertain), 86 MLP completions, 68 WAV ACKs, skipped_busy=13, short_history=15, wav_failed=0, network_failures=1.  These counters have different units; their differences are not a simple lost-WAV count because overlaps may share clips and invalid capture cannot upload.  Retained file has 108 unique candidates #27..134, 68 individual MLP records and 51 WAV ACK lines.  Of retained ML records, 50 valid two-second clips all score not_bat_candidate, and 18 incomplete clips yield fallback_original.  Valid feature/scoring elapsed time: min 18.689 s, median 19.387 s, max 22.032 s.  Source timer wraps feature extraction plus model scoring and includes scheduling/yield elapsed time; it is not pure neural-network CPU time and does not mean capture stops for those durations.  No human waveform labels supplied, so no sensitivity conclusion.

Retained event attribution: mask 1=102, mask 2=2, mask 3=4; 64 have fallback=1.  Evolved-only candidates #29 (01:40:59 NZDT, score 58) and #30 (02:15:04 NZDT, score 70) are useful review targets, not verified bats.  Priority diagnosis: repeated earlier journal quarantine/retry cause, bounded downstream feature extraction and task contention, and protection of continuous acquisition/clip history under actual event load.  Do not attribute the drops solely to WiFi, flash, evolved first pass or MLP without interval-correlated evidence.  No model promotion warranted.  Leave device reachable for remote evidence collection; no erase, reboot, firmware change or remote command was performed by this audit.

## 2026-11-14 NZDT:  GUARD-2 automated comparison completed on the physical RT

The Windows runner completed capture, score, and send in session E8B0E547 (GUARD-2, first pass evolved assist, first-pass shadow off; separate MLP in shadow, WAV on).  All three 20 s measured intervals processed every block received.  No measured DSP drops/gaps, DMA overflows, short reads, or read errors.  Diagnostic clips 1/2/3 were each 384,000 samples, continuous, zero filled=0, and acknowledged with matching HTTP responses.  The capture and score clip ACKs occurred **after** their stage END, and the send clip ACK occurred **before** END.  Final bench OFF/periodic OFF and scheduled daytime standby were observed.

| Stage | Blocks received and processed | Queue peak / 48 | Worst DSP block | Blocks over budget | Longest journal operation |
|---|---:|---:|---:|---:|---:|
| Capture | 3,750 | 13 | 9.111 ms | 58 | 182.956 ms |
| Score | 3,744 | 25 | 38.070 ms | 51 | 183.271 ms |
| Send | 3,746 | 27 | 39.280 ms | 99 | 189.198 ms |

The 20 s deltas are distinct from cumulative MIC telemetry (session high-water 47/48 by uptime 120 s; no per-operation timing correlation).  Test probes verify the diagnostic capture/transport path.  All measured intervals had candidates=0 and pulse_score_us=0.  Two run-2 candidates #4/#5 were emitted by the score-stage transition before its measured deltas; both journaled with clip_request=compare_probe_only.  They are not reviewed bats.  Preparation bypasses the normal trigger-to-clip path, including downstream inference on those candidate clips.  The previous longer session's gaps remain unresolved; do not infer WiFi, flash or the model is the cause from these timings alone.

Next discriminating comparison: same repeated trigger input in normal monitoring, evolved assist and downstream shadow fixed, WAV uploads OFF and ON.  Allow pending uploads to drain before toggling, compare per-interval MIC drop/gap and done deltas, candidate rates, completions and queue/journal evidence; restore WAV on and automatic schedule.  Short quiet tests do not qualify the field firmware.  No firmware, model or settings were changed by this documentation update.

## 2026-11-14 NZDT:  GUARD-2 serial comparison runner

Run 3 of session 7E7263A9 produced a continuous two-second diagnostic clip (384,000 samples, no zero fill, matching HTTP acknowledgement).  The owner stopped before capture END, so score/send were not run and there are no stage timing/delta measurements.  Later UNAVAILABLE was expected in daytime standby; the cumulative standby counters were flat at 857 DSP drops / 639 gaps.  Added [Windows comparison runner](../releases/rt/GUARD2_RT_Compare.zip) and [source, instructions and tests](../tools/rt_compare/README.md) to sequence capture/score/send from the board responses and retain the transcript/summary.  Host simulation verified busy retries, early/late ACKs, incomplete output, wrong-sequence rejection and cleanup.  No firmware change or flash.  Next: owner's first physical run; field promotion remains pending.

## 2026-11-14 NZDT:  first GUARD-2 loaded RT comparison, audio-loss criterion failed

Owner-supplied serial transcript SHA-256 `648ce7c77faf2aaeeda511e785af98bd84bbf99abf4c534fbf1a1dd3fd849ff4`, one session `7E7263A9`.  Run 1 entered scheduled daytime standby; `test on` resumed capture as run 2 at uptime 132 s.  No unexpected reboot or sustained stall evident before the transcript ended near 3,860 s.  The distinct profile counts below exclude the two boot-run candidates.  The 1,981 s MIC sample before the switch and 2,041 s sample after the switch have identical cumulative drop/gap counters, so the loss attribution does not rely on assuming an exact switch time.

| Run 2, about 31 min per profile | Candidate records | WAV ACKs matched by session/run/seq | DSP blocks dropped | DSP stream gaps |
|---|---:|---:|---:|---:|
| Legacy, assist off | 84 | 61 | +833 | +624 |
| Evolved assist, first-pass shadow off | 17 | 13 | +20 | +13 |

Final MIC sample at uptime 3,843 s:  853 drops / 637 gaps, processed blocks still advancing, read errors and short reads zero, legacy RX overflow stayed at its prior value of five.  The final ~17 s lack a further MIC sample.  The queue high-water mark reached 48.  Summed missing block payload alone is about 4.55 s; this excludes filter settling and is not a count of missed calls.  The two phases had different event and upload loads.  Neither the difference in drop counts nor the absence of a sustained stall establishes a causal fix or field sensitivity.

Last assist health snapshot:  87,747 fully ready and 1,702 fallback windows (98.10% of these windows), 274 budget overruns, no evolved-only hot window by that snapshot.  Of 17 assist candidate records, 16 had trigger mask 1 and one (#91) had mask 3, with journal save and WAV ACK.  No evolved-only event observed.  Bench WAV records say scoring=bypassed; these are not downstream MLP results or verified bat counts.

Two journal readback errors during the legacy phase, two active-segment quarantine messages, then a verified new write.  Event buffer cumulative flash write failures reached six with no reported RAM oldest-drop; all 84 legacy records and 16 of 17 assist records have save receipts, with the transcript ending at the last candidate.  WAV #28 failed and later ACKed on attempt 3.  No reason to erase the journal.  Status: hardware boot and linked WAV transfer confirmed; loaded uninterrupted-audio gate failed.  Next bench step is the existing serial compare prepare/capture/score/send/stop sequence to collect timing and drop deltas before attributing loss to the detector, storage or WiFi.  Leave field promotion pending.

## 2026-11-14 NZDT:  GUARD-2 confirmed running on the owner's RT

Owner serial status at 15 s uptime, session `7E7263A9`, run 1:  `NZRT-J4-GUARD-2`, NTP time, DSP and capture ON, MONITORING.  Supervisor online, safe mode off, current/previous guard fault 0.  PASS-2 applied legacy, first-pass shadow off, assist off; 479 eligible windows, 0 hot.  Downstream built-in WAV MLP enabled separately in shadow; WAV on, no completions, ACKs or upload failures.  JOURNAL-4 reports no fault or errors; detector reported zero input gaps and zero lost event records.  MLP history gaps=1; the history also clears during detector reset, so this alone is not evidence of missing DMA audio.  This confirms the installed build and a functioning acquisition path at startup.  It does not verify sustained processing under load, WAV delivery, real-world detection or overnight stability.  Next:  save separate legacy and evolved-assist serial transcripts spanning at least 30 minutes each under comparable monitoring/WAV load.  Check cumulative MIC DSP drops/gaps, guard status, selected coverage and linked event/journal/WAV evidence.

## 2026-11-14 NZDT:  GUARD-2 higher-recall RT candidate; not deployed

[Windows build-only package](../releases/rt/NZRT_GUARD2_Bench.zip) · [build, use and rollback](../firmware/meshcore_wildlife/rt_guard/README.md) · [qualification and field-audio replay](../firmware/meshcore_wildlife/rt_guard/evidence/guard2/README.md).  Based on the GUARD-1 branch at 5e57bf1.  Change scope: RT first-pass scheduling, audible FFT, opt-in union selection, event attribution, coverage telemetry, bench and optional receiver controls.  No trained weights, SD, timeline, or field board were changed.  Machine-accepted candidate hits remain unverified.  The preceding GUARD-1 owner compile does not validate GUARD-2.  Next: owner PlatformIO compile, supervised 30-minute baseline and evolved-assist board runs, then paired overnight with listening coverage, reviewed detection and false-alert rates.  Do not auto-promote.  The unobserved Nov 14 pass remains unexplained.

## 2026-11-14 (NZDT):  GUARD-1 compiled on the owner's Windows PC; field unit unchanged

The owner reported that the GUARD-1 build-only launcher completed the full PlatformIO bench build without flashing a board (`GUARD1_Bench_20261113T200748635881Z`).  The private project contains `guard_build_receipt.json`; the receipt and image hash were not independently inspected for this entry.  Next firmware gate: controlled test on physical RT hardware with microphone, radio, journal and receiver active, including disconnect/reconnect.  No hardware, field or promotion pass is implied.

Baseline night of 13–14 November:  the owner reported more similar Xiao SD and RT activity with the RT first-pass shadow off.  This was pre-GUARD-1 and describes one night.  The 20261113 timeline records AR4 `20261114_024729.bmp` as human grade 5 (bat present, species unconfirmed) with no stock AviaNZ bat candidate.  Its provisionally clock-corrected interval is 02:47:43–02:47:47 NZDT on 14 November (+14 s, not acoustically verified).  The nearby Xiao SD bar was `periodic_20261113T134518Z_00034.wav`, 02:45:18–02:45:28 NZDT: grade 1, reviewed by the owner as background only.  Its end was 135 s before the AR4 start.  No overlapping SD clip, RT candidate or RT WAV appears in the timeline.  In RT session 361DB8A8, run 3, consecutive retained candidate seq 365 (02:23:36) and 366 (03:13:10) bracket the pass.  Count as an AR4-only reviewed pass in the observed outputs.  No SD listening spans and a partial RT collection mean microphone coverage and the cause are unverified.  The periodic is a separate noise recording, not a matched negative for that pass.  First-pass shadow and downstream MLP settings are separate.

## 2026-11-13:  RT GUARD-1 resilience bench candidate

[Behaviour, build and rollback](../firmware/meshcore_wildlife/rt_guard/README.md), [emulator receipts](../firmware/meshcore_wildlife/rt_guard/evidence/emulator.json) and [Windows build-only archive](../releases/rt/NZRT_GUARD1_Bench.zip).  Baseline rt-pass1-com8 commit 4803df3.  Candidate sheds costly first-pass shadow work under pressure, distinguishes incomplete comparisons, and supervises reader, DSP, detector windows and reporter separately.  S3 fault tests include a real software restart and preservation of the reason; received field firmware remains PASS-1.  Next owner gate: full PlatformIO build, bench timing under wireless/storage load, disconnect/reconnect test and a co-located comparison night.  Receiver dead-man alarm and mandatory repository branch protection are not implemented here.


## 2026-10-17:  project baseline

### Agreed direction

The Pixel 6 Pro is the first field platform, using an EMT2 co-located with an AR4.  Process AR4 data through AviaNZ, ideally daily, to build a practical reference dataset.  Use existing and paired data to improve detection, then develop a tiny ESP32-S3 model that initially saves recordings to SD.  Validated activity will eventually feed the Bat Data Collection 2026 workflow.

The primary focus of this workstream is phone software.  Shared interfaces, dataset requirements and hardware dependencies should be recorded here for other contributors.

### Evidence from previous work

These are observations from the prior development conversation, not tests rerun during repository documentation.

- Windows WASAPI exclusive capture succeeded at 256 kHz, mono, 16-bit PCM.
- A subsequent recording showed ultrasonic energy beyond ordinary audio bandwidth.
- The user tested the desktop prototype successfully, including WAV, CSV and JSON output.
- The EMT2 works through the hub in its existing phone app.
- Native capture in our own Android app is unverified.
- The deployment extension and charging transitions remain to be tested.
- Desktop prototype source has not been imported into this repository.

### Completed

Expanded the project README and added the P6P implementation/field plan and shared handoff notes.  No Android app, model integration or hardware validation was completed in this documentation change.

### Work queue

| Priority | Task | Required evidence |
| --- | --- | --- |
| P0 | P6P capture diagnostic | Verified ultrasonic WAV, actual format, input identity and continuity report |
| P0 | USB and charging commissioning | Hardware inventory and extension/charge-transition test results |
| P1 | Background recorder and recovery | Overnight logs, valid files and explicit gaps |
| P1 | Shared event/session schema | Versioned schema and examples for both platforms |
| P1 | Daily AR4/AviaNZ comparison | Reproducible alignment and event matching |
| P2 | Existing data/recogniser inventory | Formats, labels, versions, preprocessing and reuse terms |
| P2 | Tiny-model feasibility | Agreement, memory, latency and power measurements |
| P3 | Aggregate export | Verified destination fields and recorder/model provenance |

### Requests for ESP32 and hardware contributors

- Document exact board, memory/PSRAM, microphone, sampling format and SD interface.
- Keep the capture front end independent of model choice.
- Coordinate preprocessing and event schema changes with phone work.
- Measure sustained end-to-end timing and peak memory including buffers and SD writes.
- Treat ESP32-S3 vector acceleration as CPU instruction support, not separate dedicated AI cores.
- Preserve original audio during early field evaluation.
- Do not assume AR4 spectrogram labels transfer unchanged across microphones and representations.

### Open questions

- Android version/build, hub/switch model, extension length/type and power/data topology?
- Exact AviaNZ version and bat recogniser?
- Which original WAV/annotation pairs are available and under what terms?
- Pass-grouping rule and matching tolerance after inspecting reference timestamps?
- Final aggregation fields, acceptable false-alert burden and uptime limits?

Resolve hardware questions during commissioning and other questions before their respective implementation stages.

## Handoff practice

Read the README, P6P plan, current notes and any applicable repository instructions before working.  Check recent commits/issues to avoid duplicating active work.

For each meaningful change, record the date, focus, linked commit/issue, behaviour changed, test hardware/software and inputs, results, unverified assumptions, cross-platform impact and next action.

Use GitHub issues for actionable requests and link them here.  Keep bulky recordings/datasets, credentials and sensitive site details out of Git.  Use manifests and stable dataset identifiers where appropriate.

## 2026-10-17:  ESP32 workstream onboarding

This conversation workstream focuses on ESP32 firmware, ultrasonic microphone boards, hardware testing/integration and compact model deployment.  The phone workstream and P6P-first field plan remain as described above.

Reviewed the README, P6P plan, shared handoff and recent commits through 813e351.  The repository contains planning documentation and licence only at this baseline; no ESP32 source or hardware results were verified in this review.

Created [ESP32 commissioning issue #1](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/1) to track hardware inventory, reproducible firmware, verified ultrasonic capture, sustained SD recording and cross-platform dependencies.  This update changes documentation only; no firmware was built or tested.

Next action: obtain the current ESP32 capture source, toolchain versions and exact hardware/wiring configuration.  Establish capture timing, signal response and continuity before integrating a model.  EMT2 results are separate evidence and must not be treated as validation of an ESP32 microphone board.

Requests for other contributors: coordinate session/event/health metadata and model preprocessing with this workstream, preserve source audio and label provenance, and flag choices that affect ESP32 memory, sustained processing or SD throughput in issue #1.


## 2026-10-18:  XIAO + SPH0641 ultrasonic capture baseline validated

Validated the microphone acquisition path described in [XIAO ESP32-S3 + SPH0641LU4H-1 ultrasonic capture baseline](XIAO_SPH0641_CAPTURE.md).

Hardware: Seeed Studio XIAO ESP32-S3 with an SPH0641LU4H-1 breakout based on the open-source [meerstern/SPH0641LU](https://github.com/meerstern/SPH0641LU) KiCad design.  The assembled board uses a 100 nF decoupling capacitor, R1 = 0 ohm to pull SELECT low, and R2 unpopulated.  The upstream breakout project states an MIT licence and is credited in the dedicated capture document and README.

Two independent tests used simultaneous EMT2 recordings as a reference:

- ESP32 hardware PDM-to-PCM at 64 kHz PCM / 4.096 MHz mic clock reproduced the same approximately 25.7 kHz finger-rub feature as the EMT2, with zero XIAO packet gaps.
- Ordinary I2S/MSB reception used BCLK = 3.072 MHz as a continuous one-bit sampler.  The measured raw stream was 3,068,723 bit/s versus 3,072,000 expected (-0.11%), with 49.997% one-density and zero packet gaps.  Native MSB-first unpacking reproduced the EMT2 approximately 25.7 kHz feature; alternate byte/bit orders did not.

The earlier ESP32-S3 raw-PDM receive experiments produced a persistent approximately 72 kHz framing artefact and are not part of the current design.  The project now uses ordinary I2S/MSB reception for raw PDM acquisition.

Current production direction: 3.072 MHz PDM -> native MSB-first unpacking -> CIC/FIR decimation -> 96 kHz PCM.  Keep 192 kHz as a diagnostic/reference mode until the 96 kHz pipeline is validated.  The 96 kHz target gives a 48 kHz Nyquist limit and is intended to retain the project-relevant pekapeka bands while reducing storage and processing cost.

Next ESP32 actions are no longer basic microphone bring-up.  They are final 32:1 decimation/filter validation, sustained SD capture, outdoor noise/interference testing, power measurement and eventual on-device preprocessing/inference.


## 2026-10-22:  Optional bird + bat dual-mode feasibility documented

Added [dual-mode bird and bat monitoring options](DUAL_MODE_BIRD_BAT_OPTIONS.md) as a **proposal**, not an approved hardware redesign or completed experiment.  Reviewed BirdWeather PUC/Bat Edition (remote identification), Terra Station (Linux-class local BirdNET), ESP32-S3 BirdNET-Tiny Forge, ESP32-P4, K230D neural accelerator, STM32N6 reference model and Linux gateway options.

**Current recommendation:**  Protect the validated XIAO ESP32-S3 + SPH0641LU4H-1 ultrasonic raw-I2S acquisition path.  Test ordinary-audio capture and a compact bird model on the S3 first.  If simultaneous acquisition, inference and SD writes cannot meet continuity and energy targets, investigate a companion ESP32-P4 or dedicated NPU rather than replacing the bat path prematurely.

New implementation dependencies:  independent audible microphone and capture buffers, model-specific input sample rate/normalisation, per-path timestamps and dropout counters, shared evidence schema and energy budget.  The 1,007-class global BirdNET-Tiny model is **demonstrated on STM32N6**, not established to run on S3/P4.  The supported BirdNET-Tiny Forge ESP32-S3-Korvo-2 V3.0 board is not the current XIAO.  Bird species list targets are evaluation scopes, not proven hardware limits.

**No bird microphone, model or dual-mode firmware was tested in this documentation update.**  Before committing to hardware, benchmark separate bird inference, then 24-hour simultaneous bird + bat capture and SD retention, plus per-model accuracy and Wh/day.  Any changes to sample format, I2S/DMA allocation, buffering or event schema should be coordinated with the phone and ultrasonic workstreams.


## 2026-11-08: Bat-presence lifecycle and DOC hybrid comparison plan documented

**Scope: coordination and policy only, no training/firmware/pipeline code installed.**  At owner direction, primary classification target is `IS BAT?`, not long-tailed species identification.  In owner-collected material, trustworthy FastReview grades 1/2 are no-bat, 3 uncertain, and 4/5 bat-present.  Machine-generated short-tailed species labels must not exclude otherwise eligible local recordings; owner DOC reviews provide presence only, while independently human-confirmed DOC short-tailed labels are retained as separate species evidence.

Created [model lifecycle/DOC benchmark design](BAT_PRESENCE_MODEL_LIFECYCLE.md), linked updates to [training issue #14](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/14) and [Run Daily roadmap #27](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/27).  Proposed opt-in, outside-Daily-Run candidate training from reviewed-data readiness thresholds and a frozen since-last-trained-manifest ledger; local-only versus DOC-hybrid candidate arms; fixed disjoint DOC and local holdout cohorts; append-only performance snapshots; and **manual** RT WAV shadow/active promotion and rollback after hardware parity checks.

Evidence examined in this conversation:  28,213 inventory rows, 550 grade 4/5 positives; older models trained on 94 positive plus 752 negative BMPs; current `BatDailyTool/model_progress.py` counts provisional new reviews against the Phase 1 audit and does **not** launch training.  DOC 50-recording diagnostic batch contained 46 scorable presence labels and was already used for model comparison, so it is **not** a pristine held-out cohort.  Preserve all historic comparison files and old model hashes.  Validation on owner's exact current Windows installation is still pending.

**Next patch sequence:**  snapshot and test current `training_phase1.py` and `model_progress.py`; implement grade-first bat-presence policy and a fresh verified training manifest; add candidate-queue state machine, leakage/rollback tests and DOC cohort partition ledger; train matched local-only/hybrid models offline; register frozen evaluations; only later stage RT WAV candidate shadow model.  Do not change stock AviaNZ filter, human `.bmp.data`, RT trigger or installed firmware during this planning stage.


## 2026-11-08 follow-up: WAV and BMP learning loops run on independent schedules

Owner clarified that *WAV recogniser development must improve continuously on its own schedule*, using new human-reviewed, source-linked WAV clips from the XiaoSD co-located with AR4 and from future optional RT WAV exports.  This corrects any impression that WAV learning must wait for new BMP models.  Both recognisers target binary bat presence.  Human grade 1/2 = non-bat, 3 uncertain, 4/5 bat; machine short-tailed annotations on owner data do not override human grades.  A trusted BMP grade becomes a WAV training label only for a verified BMP-to-WAV source relationship, not by timestamp proximity alone.

Updated [lifecycle specification](BAT_PRESENCE_MODEL_LIFECYCLE.md) and [issues #14](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/14) and [#27](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/27) to record independent WAV last-trained checkpoints and readiness counters, provisional 10 positive/50 negative/5 nights threshold plus 14-day cooldown, asynchronous offline fitting outside Daily Run, local-only vs DOC-audio hybrid comparisons, and RT shadow-before-active approval/rollback.  WAV formats must stay explicit: XiaoSD 96 kHz limited to <48 kHz, RT 192 kHz; assess common-band and full-band branches separately.  For DOC-hybrid models, keep train/test partitions disjoint by media and correlated capture group.

**Implementation state unchanged:** PR #24 documents optional 192 kHz RT upload and host-verified receiver controls with uploads default off; #27 still identifies the RT WAV -> BMP -> FastReview ingest as unimplemented in owner's Daily Run.  No training runner, scheduling trigger, live RT upload, model promotion, firmware flash, or existing dataset change was applied in this documentation-only update.  Before coding, review actual installed owner files and test source pairing, idempotent imports, training ledgers, locked pipeline safety, shadow compatibility, and rollback.  Record exact source changes, test receipts and device validation when implemented.


## 2026-11-08: Paired AR4/Xiao acoustic matching review and RT uploads enabled

**Owner request, design documented; no local implementation yet.**  Build an optional spectrogram-pair reviewer in Bat Daily: AR4 BMP above XiaoSD/RT WAV-derived spectrogram, physical time/frequency scales, suggested acoustic offset from existing bat_tool.py, fine horizontal drag/zoom and human decisions likely same acoustic event / not matched / unsure.  Save hashes and reviewer decisions in a new non-destructive ledger.  A time coincidence alone must never establish matching calls, species, or identity of bat; verify actual pulse patterns and overlap, and do not automatically transfer AR4 negative grades to Xiao.  Known weak candidate examples from issue #12 (r=.084, .123) are negative controls.

**Owner corrected RT operational detail:** WAV uploads are now enabled in the deployed RT settings, although the packaged PR #24 default was disabled.  The actual quantity of capture, queued/successfully uploaded WAVs, receipt acceptance and Daily Run import has not been measured in this exchange.  Poor existing RT MLP may or may not gate capture depending on deployed mode and legacy-trigger behaviour; verify trigger->candidate->capture->queue->upload->receiver counters before changing firmware.  Recommend model-independent capture plus bounded periodic audit clips (subject to power/resources) to reduce biased training selection.

Changed planning documentation [Bat-presence lifecycle](BAT_PRESENCE_MODEL_LIFECYCLE.md), [acoustic matching issue #12](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/12), and [Daily Run roadmap issue #27](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/27).  Current state: design/handoff only; no Windows BatDailyTool, training snapshot, RT firmware, WAV settings, human-reviewed data or original stock AviaNZ files modified in this work.  Implementation should inspect exact owner-local tool/receiver source, build non-destructive reviewer prototype, run controls, and document source hashes, tests, installation state and rollback.


## 2026-11-08: Next RT firmware and model paired maintenance plan

Owner would like to prepare periodic independent WAV sampling in the next RT firmware update (if firmware change is actually necessary) and install the next evaluated WAV candidate model during the **same maintenance visit**.  This is coordinated deployment, not coupling of the WAV model training schedule to firmware releases.  Wi-Fi inactive-slot numeric model updates should continue independently where compatible.

Proposed audit sampling baseline: randomised 2-second 192-kHz mono PCM16 WAV approximately every 20-30 minutes during monitoring, bounded by measured RAM/storage/power/Wi-Fi costs and no disruption to sensitive legacy event-triggered capture; distinct event/audit provenance.  A 12-hour night would contain about 24-36 WAV clips or 18-28 MB at that rate.  Audit recordings have **no bat/no-bat label until human review**; explicitly measure failures, capture gaps and missed model detections.  Confirm actual device mode before claiming weak MLP is suppressing capture.

Release gates: verify local current firmware and receiving path, compare frozen local and DOC audio test cohorts to incumbent, stage signed/hash-checked candidate and firmware with independent rollback, ensure default new WAV model is SHADOW, and after a monitored trial seek explicit owner approval for ACTIVE.  An RT firmware flash does not fix Daily Run RT WAV -> BMP -> AviaNZ -> FastReview integration, which remains a separate verified dependency.

Updated the [model lifecycle](BAT_PRESENCE_MODEL_LIFECYCLE.md) and GitHub issues #14 and #27.  **Documentation only.**  No firmware, capture setting, WAV file, model or Daily Run installation has been changed by this conversation turn.


## 2026-11-08: RT periodic WAV capture must be a remote command

Owner confirms periodic independent WAV capture should be an **operator-commanded, persistent RT setting**, analogous to existing WAV upload/ML mode/model controls, rather than always running after firmware install.  Proposed readback/set controls: enable/disable, interval minutes, clip duration seconds, timing jitter, max clips/night and optional periodic upload toggle.  Need authenticated/persistent command handling, validation/ACK, delivery/skip counters, and model-independent triggering.  Record distinct provenance of unlabelled periodic audit clips.  This is NOT implemented firmware; exact command syntax must be matched to the existing RT parser after its source and live version are inspected.

Owner's reported 15,000 input recordings and ~9,000 AviaNZ candidate files reflect ~60% candidate rate, with 364 actual verified bat passes (passes are not necessarily unique positive files).  Do not report 364/9000 as AviaNZ classifier precision or equate local 220-recording BMP model validation with deployed RT WAV MLP.  Historic local MLP/CNN BMP dev validation 27/28 TP with 1/192 and 30/192 FP respectively; external DOC 46-recording BMP diagnostic MLP 4/12 TP with 1/34 FP, CNN 5/12 TP with 3/34 FP.  Correct comparison requires original built-in AviaNZ and frozen models scored on *same* human-reviewed independent source recordings, ideally full pre-filter negatives/periodic audio, with file-vs-pass denominators noted.

Updated lifecycle spec, PR #24 firmware design notes and Daily Run issue #27; no RT firmware, command parser, live settings, recorded data, model or installed Daily Run code changed.  Model and periodic-audit feature can be staged together during a later owner-approved device maintenance window.


## 2026-11-08: Stock AviaNZ baseline reporting correction

Owner correctly noted that stock AviaNZ automatic notations were saved and should provide an explicit control in **every** new model report; the older use of `unknown` for its precision/recall should be replaced with a disciplined original-baseline extraction and coverage status.  Machine `Long-tailed bat`, `Short-tailed bat` and mixed labels are positive calls for binary `IS BAT?` evaluation but cannot override the owner's human grade (1/2 non-bat, 3 uncertain, 4/5 bat) or cause short-tailed exclusion in training.  Preserve original auto `.bmp.data` baseline in `Backup`, filter/config/code hash and source-media identity; the edited current sidecar is not trustworthy as a historical snapshot.

Read-only analysis of supplied `/mnt/data/review_inventory(1).csv` (SHA-256 6d50eee8dbb8568640ee8e158ed69ea5aa9887394b301a4b3a458613864eb5a9): 28,213 rows; `baseline_provenance` isolated_cli_batch=3,122, gui_batch_confirmed=192, unknown=85, missing=24,814; nonempty machine_species_annotations=369 (73 long,196 short,100 both), of which 339 have human grade 1/2, 13 grade 4/5, 13 grade 3 and 4 no grade.  These are machine/human disagreements on a selected subset, **not** stock recogniser precision/recall.  The owner-reported ~15k originals -> ~9k AviaNZ candidate files -> 364 verified bat *passes* has different denominators and needs review of unflagged originals before recall is claimable.

Created a conversation-only provenance audit bundle `AviaNZ_Baseline_Provenance_Audit_20261108.zip` with recorder-level counts, explicit machine-grade cross-tab and limitations.  Updated [bat-presence lifecycle](BAT_PRESENCE_MODEL_LIFECYCLE.md) and issues [#13](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/13), [#14](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/14), [#27](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/27).

**Next implementation actions:** scan actual original per-recorder Backup sidecars and run logs without edits; join with hash-verified original media, separate candidate-selection and machine auto bat annotations, human grades and event/pass groups, audit random unflagged original recordings; then patch owner-local `BatDailyTool/model_progress.py` and recogniser evaluation reports to show stock AviaNZ on exactly the same held-out cohorts and explicit missing/unscorable denominators.  No code, running tool, reviewed annotation, RT firmware or fitted model modified in this turn.


## 2026-11-09: Functional AR4/Xiao per-night acoustic calibration pilot, not installed

Delivered a tested, opt-in AR4 ↔ XiaoSD acoustic pair reviewer ZIP for the owner's current goal: manually inspect one/two stacked spectrogram pairs, slide Xiao in time and mark matching/rejected/uncertain; confirmed shared acoustic events calibrate **per-night** AR4 timing without changing the global recorder clock, and immediately recompute the reviewer's temporal overlap candidates. Xiao session-estimated UTC (when present) supersedes rounded WAV filenames in suggested comparisons and can be used by the guarded legacy core.scan hook. A guessed match is never a biological or species confirmation.

Artifact: `BatDaily_Acoustic_Match_Calibration_v1.zip`, SHA-256 `340ea37db410b0fc1d03058efebdf9fa32a691a43b52d9bbba179469e1fc41fe`, with `acoustic_pair_calibration.py`, `install_acoustic_review.py`, `Run Acoustic Match Review.bat`, README and tests. Exact script hashes and implementation details in [AR4/Xiao acoustic calibration pilot handoff](AR4_XIAO_ACOUSTIC_MATCH_CALIBRATION_V1.md). ZIP is attached to its ChatGPT creation conversation; no user data in the artifact. Source only collected from archived BatDailyTool v1.9.5 for test, not fetched from the owner's live PC.

Evidence/tests: 9 unit tests pass; loopback HTTP reviewer displays generated BMP/WAV PNG and accepts match/reject/unsure with SHA ledger; version-safe installation and hash-checked rollback pass on archived v1.9.5; patched archived `bat_tool.scan` successfully recovered a synthetic 17-second-misaligned pair without turning a silence-only waveform into a confirmed acoustic match. Reviewer's proposals update immediately; cached legacy `Matched/Pairs` plots and generated timeline await the next deliberate scan/refresh of the affected night (completed historical receipts may skip them).

**Not yet installed or verified in owner-local Windows BatDailyTool.** Installer's first step is `--dry-run`, which refuses unknown current source; `--standalone-only` preserves optional viewer without the Daily Run hooks if version mismatch. Backups are kept under `BatDailyTool/Program_Backups/acoustic_review_*` and rollback checks hashes. No original WAV, BMP, `.bmp.data`, Backup, grade, model, RT firmware or stock AviaNZ files changed.

Owner-side acceptance: test actual current `bat_tool.py`/`daily_timeline.py` integration, inspect one or two real 2026-11-08/09 matched pulse sequences, verify per-night recalculation and no false matches, run Daily Run safety/regression, record installation receipt and exact tool versions. Existing RT receiver-only WAV files are not yet supported in pair reviewer until source names/timing receipts are validated. Coordinated issues [#12](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/12) and [#27](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/27).


## 2026-11-09: Optional AR4/Xiao reviewer v1.1 corrected after live owner feedback

User demonstrated two real optional reviewer behaviours in screenshots after installing earlier v1 pilot: delayed spectrogram rendering without a loading indicator; manual/suggested match at 0.672 seconds jumping back to 0.908 seconds after accepting a match and recomputing per-night clock estimate. The user also rejected background/noise-only matching as an unnecessary review burden; acoustic calibration should target **bat-call evidence**.

Created and tested `BatDaily_Acoustic_Match_Calibration_v1_1.zip` (SHA-256 `9163d5d9928623d992a0666330a615d5166c5e0ca3ac60b1eb808174f4564142`, 27,130 bytes). Source `acoustic_pair_calibration.py` SHA `6b931dc95c6baf973c2c55c0ba268854482e124e4917de88b7c749d3f10b6ba8` and guarded updater `update_acoustic_reviewer_v11.py` SHA `25c0f247138dbf97edbf87895c88db3d5fabbd173d31bac43e4253a3fb6693f2`. Includes README, CHANGELOG and 13 unit tests. New code limits default queue to trusted AR4 grade 4/5 or accepted legacy human-reviewed bat, with explicit optional grade 3 or ungraded machine calls; removes known human negative Xiao from suggested matching. Loading/error overlays and exact saved-manual-shift restoration work, preserving old calibration ledger and Daily Run hooks.

Validation: 13 Python tests; Chromium JS test with stubbed API preserved manual shift 0.672 seconds after save and reload; 96/192-kHz render tests; updater dry-run, idempotent swap and rollback on original v1 source SHA. Hosted Chromium navigation to a real localhost test server was blocked by browser administration, so **not** a production browser/device test. No changes made on owner's Windows computer, reviewed source files, firmware or installed Run Daily. Existing v1 installation still user-owned. Upgrade with `py -3 update_acoustic_reviewer_v11.py --root "C:\Users\revje\Documents\Bat" --dry-run` then without dry-run only if ready, while Daily Run and optional reviewer are closed. Unknown local module hash fails closed; submit installed module for reconciliation rather than overwriting.

Changed coordinating [acoustic calibration handoff](AR4_XIAO_ACOUSTIC_MATCH_CALIBRATION_V1.md) and [issues #12](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/12) / [#27](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/27). Next agent must confirm exact owner installation hash/receipt and test a real bat-positive pair, plus Daily Run normal and old-night regeneration safety before marking integrated. RT receiver-only WAV support remains unimplemented. No extra daily review requirement.
