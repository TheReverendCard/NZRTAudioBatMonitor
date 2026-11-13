# Shared development log and handoff

## 2026-11-13:  Emulator tests and trainer coverage (v2, PR #48)

[Install, operate and reproduce](../tools/s3_candidates/EMULATION.md).  [Test receipts](../tools/s3_candidates/evidence).  [Windows installer archive](../releases/tools/Bat_S3_Emulator_Training_Guard_v2.zip).  New: known trainer BATs guard frozen inputs, Daily/exports report prediction coverage, optional WSL worker verifies S3 builds; digest-bounded first-pass replay with gap/reset tests.  Two genuine trained models tested on supplied media; four other trained-family adapters tested with fixtures.  Existing desktop fail cases and RT drop telemetry are recorded separately.  Windows/WSL owner installation and live RT timing still unverified.  Production firmware and selected detectors remain unchanged.  Next: new frozen nights, capture replay on a spare RT under radio/storage load, and separate board acceptance before promotion.

## 2026-11-13:  ESP32-S3 candidate outputs

[Installer, scope and rollback](../tools/s3_candidates/README.md) and [verification evidence](../tools/s3_candidates/VALIDATION.md).  A local install exports existing and future model runs and records readiness in Daily_Run_Reports/S3_Exports/index.json.  Six model families and seven first-pass, event-ranking and replay profiles have S3 source exports.  Only a compatible WAV MLP has the receiver's weights format.  The reported device selection remains legacy active / first-pass shadow off.  This revision was not flashed or installed on the owner's PC.  Next: link the diagnostic projects, run matched board/field comparisons, then review any shadow or active change separately.

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
