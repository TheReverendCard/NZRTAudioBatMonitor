# BatDailyTool incremental folder/task checkpoints v1.2

**Updated 2026-11-09.  This is an implementation handoff, not owner-field validation.**

## Why the release exists

The owner ran the installed v1.1 Final Review launcher.  After `POST-DAILY RESULT: COMPLETE`, it remained silent for about ten minutes at `Saving a validated input snapshot for fast repeat runs...`.  The original v1.1 `daily_change_guard.py` did two archive-wide `gather()` passes, then reread original WAV/BMP bytes from the latest pipeline receipt and serialised a very large global JSON state.  The owner used `Restore Previous`, returning to the **OneClick v1** launcher.  The goal is to avoid another heavyweight global checkpoint and make unchanged repeated daily runs fast while protecting old reviewed data.

## Actual deliverable, identity and install scope

- **Owner-facing complete, executable source ZIP:** `BatDaily_Incremental_RunDaily_v1.2.zip`, 34,391 bytes.  SHA256 **`5d72cb9aa88f3bd88796c609cbb0e11d3e6c5baf137e2e9d5c95ee321cbfc1da`**, 17 files.  This code is attached in the conversation, **not committed to this PR**.  `FILE_HASHES.json` inside ZIP authenticates every other file, and `MANIFEST.json` pins exact versions expected on Windows.
- Owner's **restored v1** expected installed files: `BatDailyTool/Run Daily with Final Review.bat` SHA256 **`11cf5a4cb687bb00e24a65b4a33a3b27908a0a5c2779810e9732ff6211995a1d`**, `Run Daily Scan.bat` SHA256 **`a1d7149f550a2b6384809302644ea079b41279fe9c90aa9ab008fd8e81cbb3d0`**, and dependency `post_daily_sync.py` SHA256 **`9104d02914aa865adf0e75b051d9ced62faa80c52f8597f8f3f960473feba039`**.
- Candidate output source SHA256 after guarded installation: `daily_incremental_v12.py` **`b3ef[SEE ZIP MANIFEST FOR EXACT]`**; final and scan batches in ZIP's `MANIFEST.json`.  Do not hand-apply unverified hashes.
- The installer changes only those **two .bat launchers** and creates one **`daily_incremental_v12.py`**.  It does **not** edit `daily_pipeline.py`, `finish_daily_reviews.py`, `post_daily_sync.py`, `verified_activity.py`, reviewed `.bmp.data`, original BMP/WAV, AviaNZ machine backups, Xiao firmware or fitted model assets.
- The source-controlled handoff here is **documentation-only**, not a complete code PR.  Source of truth for exact full package bytes is the attached ZIP and its component hashes.  Do not merge this documentation to default as evidence of an installed implementation.

## Implemented behavior in the ZIP (not yet owner-tested)

1. **Per-folder SQLite journal:** `Daily_Run_Reports/Daily_Integration/Incremental_State_v3.sqlite3`, storing folder paths/site roles and file path, size, ns mtime/ctime, file identity, logical source role, independent task receipts.  Read-only one-pass stat inventory on seal; update **only changed SQL file rows** inside a transaction.  No repeated global gather, no routine full-media SHA reads and no multi-MB global JSON dump.  A long walk reports progress every ~6 seconds.
2. **Preflight routes:** return code 10 UNCHANGED; 11 REVIEW_ONLY when authenticated human grade/queue changed; 12 REPORT_ONLY for model/artifact/manual acoustic decision or required report output change; 0 FULL when raw media/External Data/import/config changed or state is untrusted; 2 BLOCKED for an active daily lock.  Clock date alone does not force FULL.
3. **Task-aware caching:** independently checkpoint `sd_import` and `sd_prepare` with separate relevant input+control metadata signatures, required output JSON SHA and completion state.  Input changes, missing converted BMP, changed report output or script version invalidate.  The existing `daily_pipeline.py` remains the protected core on a genuinely changed-source FULL run.
4. **No independent run-daily launcher:** the same `Run Daily with Final Review.bat` executes normal review sync and the existing `post_daily_sync.py` (including human-reviewed inventory, Shed-only verified dashboard and five v2-model cached predictions).  An unchanged path doesn't open Fast AviaNZ; review-only doesn't rerun the acoustic import.  It keeps a single index entry point.
5. **Existing COMPLETED receipts may be seeded:** `Seed Existing Completed Reports.bat` only accepts existing `Daily_Integration/latest.json` COMPLETE plus source day receipt COMPLETE, required HTML and source metadata not newer than previous post time, with no running daily lock.  It refuses ambiguous/source-newer state rather than claiming previous work.  It does not run AviaNZ or model inference.
6. **Optional deep audit** hashes the newest completed night's original media against original per-day receipt on user request.  The normal metadata scan is not cryptographic proof against adversarial same-size/unchanged-timestamp replacements.
7. **Guarded preview/installer/restore:** `Preview Update.bat`, `Install Update.bat`, `Restore Previous.bat`; backup exact original source bytes into a new dedicated `Daily_Integration/v12_backups/<UTC>`; atomic replacement; refuse wrong hashes, owner-modified files, NTFS reparse targets.  The old v1.1 backups are not mutated.

### Actual testing

**31 Python unittest cases passed** in the tool container on 9 November.  Tests cover all route decisions, new historic AR4/source imports, model-only changes, current human vs machine annotations, missing report and incomplete post receipt, directory deletion, active lock, task receipts, protection of owner-reviewed sidecars, existing-successful report seeding, checksum-guarded install/restore and a 2,000-file synthetic sample.  ZIP CRC and per-file content SHA verified.  **No actual Windows cmd.exe execution or measured owner-disc 30-second repeat test yet.**  Synthetic tests are not field acceptance.

### What remains unresolved

- The internal owner-current `daily_pipeline.py` and `finish_daily_reviews.py` versions have not been byte-verified for in-place patching.  They still scan/process more than is ideal on a new-source FULL run.  For now only the outer SD import/prep stages get reusable task receipts; the core needs an independently guarded per-night/per-recording refactor.
- The owner wants an **unchanged repeat in ≤30 seconds**.  Must measure on their Windows storage; metadata stats for tens of thousands of files may still take longer.  Do not invent success.
- Historical 3,538 machine backup gaps, two original zero-byte BMPs, legacy conversion conflicts, unreviewed RT audio and recorder acoustic alignment are separate unresolved tasks.  DOC/local frozen independent model tests remain separate; do not quietly promote a v2 shadow model.
- A single late AR4 SD-card import still invokes existing core processing.  The SQLite snapshot itself updates only affected file/folder records and does not hash all prior media.

### Owner first run

1. Since v1.1 was restored, unzip separate from `BatDailyTool`.  **Preview Update.bat**, require no blockers.  Then **Install Update.bat**.
2. Optional **Seed Existing Completed Reports.bat** before normal daily processing, but only if last successful reports have no newer inputs.  If refused, run normal Final Review once.
3. Run exactly the same `Run Daily with Final Review.bat`, inspect `incremental_seal_latest.json`, and repeat with unchanged inputs.  Expected return `INCREMENTAL: UNCHANGED`; record real elapsed time, file count and reasons for FULL/REVIEW_ONLY.
4. After changing one valid grade, expect REVIEW_ONLY, no acoustic rescan; after adding a WAV/old AR4 card expect FULL and correct source provenance.  `--force` bypasses caching.  Source-only restoration via Restore Previous is available.

Related: #35 per-file performance, #38 v1.1 issue, #37 one-click Final, #27 Run Daily roadmap, #36 model pilot.
