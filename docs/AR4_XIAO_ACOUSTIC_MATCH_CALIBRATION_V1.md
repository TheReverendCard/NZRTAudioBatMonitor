# AR4/Xiao acoustic matching calibration pilot v1

**Date:** 2026-11-09 NZ. **Status:** Built and tested as downloadable ZIP in a ChatGPT conversation; **NOT installed or field-tested on owner's Windows BatDailyTool**. This document is a precise handoff, not an assertion that the current Daily Run has been changed.

## Owner's problem and accepted workflow

The 2026-11-08/09 Daily Timeline shows AR4-confirmed bat recordings and XiaoSD / RT event patterns. The existing BatDailyTool v1.9.5 `bat_tool.scan()` selects AR4↔XiaoSD candidates only when clock-adjusted file intervals already overlap within configured ±2 s, then searches ±2 s in 2 ms steps for 24–42.5 kHz envelope correlation. It therefore excludes potential real shared calls when clocks are initially wrong. Additionally, `daily_timeline.source_rows()` may use precise Xiao `CLIP start_est_utc_us` session estimates whereas old `bat_tool.wav_info()` uses rounded UTC filenames.

Owner wants an **optional** visual reviewer, not a daily review obligation: stacked AR4 BMP and Xiao WAV spectrograms; horizontal/manual shift; accept “I think same acoustic event”, reject or unsure. One or two accepted acoustic events should derive a provisional night offset/drift and immediately recompute candidates/overlap opportunities. No machine detection or grade label should be silently changed.

## Delivered artifact and exact implementation status

Artifact ZIP: `BatDaily_Acoustic_Match_Calibration_v1.zip` (22,276 bytes; SHA-256 `340ea37db410b0fc1d03058efebdf9fa32a691a43b52d9bbba179469e1fc41fe`).

Contains:
- `acoustic_pair_calibration.py` (SHA-256 `73fc3a7b3b2d27ca92ad8e16b97ee541f8d8388fba903ec65b369268d731dcaa`) with loopback-only local HTML reviewer, list of top nearby candidates, real 18–46 kHz spectrogram displays with common seconds/Hz scales, mouse/slider manual shift, optional exploratory 24–42.5 kHz envelope-correlation alignment, manual match/reject/unsure, SHA-bound append-only review ledger, per-night offset/drift fit and immediate candidate-recomputation JSON. Supports 96/192 kHz mono PCM16 WAV with appropriate spectrogram sample rate.
- `install_acoustic_review.py` (SHA-256 `636af35c06a3eb04de55bb70da64215f66e206d1ea3e39e9ddfebd5ed8f99edb`): guarded source insertion into existing `BatDailyTool/bat_tool.py` and `daily_timeline.py`. Reads both current files, matches exact old-code anchors, Python-compiles proposed changes, backs up originals with hashes/receipt before writing, then copies optional reviewer and launcher. Aborts without changing source if anchors differ; `--dry-run`, `--standalone-only`, and hash-safe `--rollback-receipt` supported.
- `Run Acoustic Match Review.bat` (SHA-256 `fa71704edb357b2c7744dc465d8d6f8d43324db31024c93c88917d10d96ef2e6`): launch from user's existing BatDailyTool virtual environment.
- `README.md` with installation, safety, limitations and rollback; `test_acoustic_review.py` with regression tests.

### Behaviour and authoritative evidence

- Saved decisions: `Bat/Matched/Acoustic_Calibration/anchor_reviews.json` with both original source media hashes, review state, adjusted relative shift, reviewer, note and UTC history. No existing review sidecars/Backups/config are modified.
- Latest recommendations: `YYYYMMDD_suggestions.json`; recomputed immediately after each decision. A single anchor fits **provisional constant offset**; two independent-time anchors can fit a bounded drift (reject impossible >1500 ppm, flag >2s disagreement).
- Source start times prefer authoritative XiaoSD session `CLIP start_est_utc_us` estimates where available, else WAV filename UTC. This avoids mistaking a filename-vs-session discrepancy for AR4 clock error.
- In **integrated mode only**: existing normal `bat_tool.scan()` uses calibrated AR4 time when preselecting candidate overlaps, and cached Matched plots are invalidated when either source time basis or calibration version changes. `daily_timeline.source_rows()` projects the corrected AR4 times. No global `config.json` time changes.
- Historical days are not automatically replayed. Reviewer rebuilds **its own** candidate list immediately. Existing `Matched/Pairs` plots regenerate when `bat_tool.scan()` next processes the night. A completed historical Daily Run may intentionally skip it.
- Calibrated *time overlap* is not proof of a common biological call; low-correlation/timing-only pairs remain weak. No bat/species identity or grades copied from AR4 to Xiao.
- Matching v1 discovers AR4 BMP and XiaoSD WAV under the normal dated folders. RT receiver-only audio under `WiFi_Backup/RT_Clips` is **not** yet supported until receipts/names/time bases have been confirmed. RT timeline-only ticks are not acoustic evidence.

## Tests actually performed

1. Nine unit tests passed: synthetic 17 s hidden timing gap recovered by one review; correction revoked; stale source SHA refuses anchor; inconsistent anchors do not invent drift; two separated anchors fit moderate drift; 96/192k spectrogram rendering; session-estimate priority; silent WAV never produces a confident acoustic fit; v1.9.5 syntax-safe/idempotent source insertions.
2. Local reviewer HTTP smoke succeeded on synthetic WAV/BMP: served HTML, candidate JSON and real PNG, optional acoustic suggestion, SHA-logged human match via POST, immediate refit to 17s.
3. Guarded installer dry-run, install, idempotent recheck and SHA-verified rollback all passed against extracted `BatDailyTool_v1.9.5_AutoCLI_RTWiFi_SafeDaily.zip` without touching the owner's actual files.
4. End-to-end **synthetic legacy core.scan smoke**: one confirmed 17 s anchor caused archived v1.9.5 `bat_tool.scan()` to regenerate one candidate pair previously absent, correctly flagged `timing_only_or_weak` with no acoustic correlation from silence. No source recordings/grades changed.

## Required owner-side verification

- [ ] Extract ZIP, run `py -3 install_acoustic_review.py --root "C:\Users\revje\Documents\Bat" --dry-run`. If current code no longer matches, do not patch forcibly; use `--standalone-only` and submit current `bat_tool.py`/`daily_timeline.py` for precise integration.
- [ ] Stop Daily Run before installation. Run guarded installer only after compatible dry-run; preserve Program_Backups receipt.
- [ ] Launch optional review on a recent night. Confirm one visually clear AR4↔XiaoSD shared acoustic call; record manual offset and source hashes. Accept a second temporally separated matching call to estimate drift, if possible.
- [ ] Confirm app recomputes candidate overlaps and never turns no-match into a negative-grade recording. Compare newly suggested pairs against the earlier r=.084/r=.123 weak cases.
- [ ] Verify next actual Daily Run processes a new date safely, preserved backed-up annotations, no duplicate pair recording/review and correct AR4/SD event positioning. Use explicit older-day reprocessing protections for completed historical dates.
- [ ] Test rollback on the installed source with original hashes if needed; document exact installed source/model/firmware and environment versions.

### Coordination

Track this in issue #12 (acoustic alignment), issue #27 (Daily Run), issue #13 (review safety). This is an optional calibration feature and not a new model, training data, species assignment, RT firmware modification or deployment.

**Current status remains: pilot ZIP built/tested locally; installation and owner field validation pending.**


## 2026-11-09 update v1.1: loading, stable saved shift, bat-only review queue

**Owner field feedback:** v1's paired spectrograms appear blank before image generation; after automatic suggested acoustic fit (example 0.672 s), clicking the positive review snaps back to newly fitted clock-estimate shift (example 0.908 s); user also does not want routine background-noise alignment. These are directly reported in 2026-11-09 screenshots.

**Deliverable:** `BatDaily_Acoustic_Match_Calibration_v1_1.zip`, SHA-256 `9163d5d9928623d992a0666330a615d5166c5e0ca3ac60b1eb808174f4564142`, 27,130 bytes, generated in the ChatGPT project conversation. Changed module `acoustic_pair_calibration.py` SHA-256 `6b931dc95c6baf973c2c55c0ba268854482e124e4917de88b7c749d3f10b6ba8`; update installer SHA-256 `25c0f247138dbf97edbf87895c88db3d5fabbd173d31bac43e4253a3fb6693f2`. Full README, change log, source and tests inside artifact. This **replaces only the optional reviewer module**, not original Daily Run scripts.

**Implemented in the v1.1 package:**

1. Each track has `Loading ... spectrogram` overlay, then hides on PNG load or shows a clear error. It resets on pair change.
2. Reviewer captures the actual manually selected/algorithm-suggested Xiao shift before POST. After positive decision and per-night refit it reloads with the exact previous UI shift; on later reopening it prefers SHA-valid `saved_match_shift_seconds` to recalculated `initial_shift_seconds`. The clock suggestion remains separate information. An already accepted pair can be changed to Not a match to revoke the anchor with ledger history preserved.
3. Default review scope is AR4 with trusted human grade 4/5 or legacy accepted human-reviewed LT bat. Optionally expand to human grade 3 or ungraded machine bat candidate. Owner human grades 1/2 exclude AR4 even if AviaNZ predicted machine short-tailed; independently graded Xiao WAV/BMP grade 1/2 is also excluded. Ungraded Xiao WAVs remain potential partners to true AR4 bat calls. The match engine still does not assert shared bat identity from timing/correlation.
4. Optional reviewer supports same cached clock anchors, source SHA checks and 96/192 kHz WAV display. Normal `bat_tool.scan` integration established by v1 continues unchanged.

**Update command (owner PC only; no update applied remotely):** Stop the reviewer and Daily Run; extract ZIP; `py -3 update_acoustic_reviewer_v11.py --root "C:\Users\revje\Documents\Bat" --dry-run`. It accepts exactly the known v1 `acoustic_pair_calibration.py` SHA `73fc3a7b3b2d27ca92ad8e16b97ee541f8d8388fba903ec65b369268d731dcaa` or reports already updated. If ready, run without `--dry-run`. Refuses altered/unknown source and does not force a patch. Original module saved with SHA-verified rollback receipt under `BatDailyTool/Program_Backups/acoustic_reviewer_v11_*`; preserves `Matched/Acoustic_Calibration/anchor_reviews.json` untouched.

**Verification performed:** 13 Python tests pass; headless Chromium with a mocked API confirms accept-at-0.672 and restoration-at-0.672 despite backend model refit (direct loopback navigation was blocked in hosted browser); render_image PNG tests for 96/192 kHz inputs; updater dry-run, idempotent install, rollback smoke pass against the exact original v1 hash. No owner Windows installation test or real field audio comparison has been performed. Reviewer-only module updated; no firmware, source recordings, AviaNZ reviews or training data touched.

**Owner-side checks still needed:** verify dry-run source version; install v1.1 safely; open AR4 human grade-4/5 bat candidate, see loading states and both spectrograms; press automatic suggestion and accept; ensure shift stays identical and reopens unchanged; try optional grade 3/machine candidates; confirm noise-grade AR4 and Xiao files absent; verify next Daily Run has no new errors; record install receipt and real recorded match. RT receiver-only WAV ingestion remains a separate pending workstream.
