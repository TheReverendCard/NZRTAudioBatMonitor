# Verified Bat Activity dashboard and spreadsheet export: v0.1 implementation handoff

**Date:** 8 November 2026. **State:** standalone Python implementation, offline HTML UI, XLSX+CSV exports and guarded A2.2 Run Daily integration created/tested locally, delivered as ChatGPT ZIP **but NOT yet installed on the owner's Windows machine**. This is not a field-verified release, and it does not complete all of #27.

## Original user request and example

User wants calendar-by-night heatmap of **explicit human grade 4 or grade 5** bat-positive recordings across the Shed array and a copyable Excel export matching the uploaded `DetectionSummary_Long_tailed_bat(2).xlsx`. The attached workbook has three original sheets:
1. `Time Stamps`: `File Name`, `start (hh:mm:ss)`, `end (hh:mm:ss)`, `min freq. (Hz)`, `max freq. (Hz)`, `certainty`, `call type`, `number of overlaps`.
2. `Presence Absence`: `File Name`, `Present?`, `Certainty, %`.
3. `Per Time Period`: `File Name`, `Page`, `Maximum certainty of species presence (0 = absent)`.
The new export preserves these names and headers. It adds `Review provenance` with site, source recorder, explicit human grade, reviewer, species/label, original source and datetime evidence. **Grade 4/5 is a verified recording-level bat presence decision, not proof of species or precisely timed call segments.** Never convert grade into invented percent certainty.

## Source package and integrity

- Delivered artifact: **`BatDaily_Verified_Bat_Activity_Heatmap_Export_v0.1.zip`**, SHA-256 **`a64fdfcdd250acb9ea20333ea55a1cbd4ce16cc1925bc2038d69a1ec1f84cfc0`** (~45.9 KB). Source ZIP is in the ChatGPT conversation; **NOT committed to the repo**. No local Bat collection data is in the ZIP.
- `verified_activity.py` source SHA-256 **`ece11d1fccad405072c35b8e107601db4753b3108acfb7387a2d37721570f5a4`**; 510 lines, Python stdlib and `zoneinfo`, no third-party runtime package.
- `install_verified_activity.py` SHA-256 **`8a666e4ab312bfcc4c57efc88c5064ce8d53cda6347ba48adfe4df88d27a5da6`**; version-gated preview/install/restore.
- `README.txt` SHA-256 **`c3eb115f94ee4b1ab680f818b47eaa255dd737c650228ed9d7f30c483d6a7612`**.
- `Preview Verified Dashboard.bat`, `Install Verified Dashboard.bat`, `Restore Verified Dashboard.bat`, `Open Verified Bat Dashboard.bat`.
- `tests/test_verified_activity.py` and read-only A2.2 source reference snapshots under `tests/fixtures/`; `MANIFEST.json` includes all packaged file checksums. ZIP CRC verified.

## Source eligibility, accounting and segregation

- Scan all **canonical Shed** date folders under `Bat/YYYYMMDD/AR4YYYYMMDD`, `XiaoYYYYMMDD` and `XiaoRTYYYYMMDD`; XiaoRT additionally requires `.rt.json` provenance. Never ingest South, Other or arbitrary External Data into Shed heatmap.
- Explicit `.bmp.data[0].BatDailyReview.grade` **int 4/5**, source `avianz_gui_hotkey`, and matching human reviewer metadata. Machine-only AviaNZ, grade 3, reviewer-ambiguous legacy, absent sidecars and invalid time/duration do **not** count. Source BMP must be nonzero-length.
- Local `Pacific/Auckland` night labelled by **evening date** (12:00→12:00 boundary). AR4 clock from local filename (marked unverified recorder time); XiaoSD/RT from compatible UTC receiver metadata or UTC filename. No speculative AR4/Xiao offset. DST: iterate true UTC minutes, then map to NZ local clock so clock-repeat doesn't collapse different true minutes.
- Ten-minute heatmap cells, default **16:00–09:00**, optional full 12:00–12:00, colour 0–10 number of **distinct minute intervals containing positive recording audio**. Recorder duplicates count once per actual minute while all source records remain clickable. A minute overlapping a positive recording is **not** a count of individual pulses or bat passes. The view also has date range, grade 4/5 filter, clickable cell with source links, searchable record list, time-of-day positive-night histogram, local file paths and diagnostics.
- Fill every calendar day between the earliest and latest canonical recorded dates. **Blank/zero means no confirmed grade4/5 recording in available data, not a verified negative or full listening coverage**; coverage denominator is not calculated. Site privacy: no site coordinates in HTML.
- **South separately optional export only**: source is the proven `south-ar4` rows in A2.2 `Daily_Run_Reports/External_Import/imports.sqlite`, with managed `.bmp.data` explicit human grade. `Other` excluded; new external Shed AR4 that is not reconciled into canonical Shed date folders still excluded from Shed plot to avoid double-counting.

## Generated outputs

Under `Bat/Daily_Run_Reports/Verified_Bat_Activity/`:
- `index.html` self-contained offline interactive dashboard (no server, CDN or network).
- `DetectionSummary_Grade4_5_Shed.xlsx`, `DetectionSummary_Grade4_5_South.xlsx`, `DetectionSummary_Grade4_5_Shed_and_South.xlsx` (first three workbook sheet names and AviaNZ columns preserved, fourth audit sheet).
- `Verified_Recordings_Shed.csv`; `diagnostics.json`.

All outputs are atomic generated report files. Originals, machine backups, reviewer sidecars, active detectors and ML models are read-only. Time Stamps exports one row **per grade4/5 recording window**; it is NOT a re-annotation of individual pulses. Certainty/frequency from actual positive bat-labelled segment fields only, left blank if unavailable; grade is on separate provenance sheet.

## Installation modes and exact A2.2 hooks

**Standalone (no installed source edit):** `Open Verified Bat Dashboard.bat` executes `py -3 verified_activity.py --root "%USERPROFILE%\\Documents\\Bat" --open` from extracted folder.

**Guarded A2.2 integration (owner opt-in):** `Preview Verified Dashboard.bat` first. Requires actual installed A2.2 normalized SHA:
- `BatDailyTool/daily_pipeline.py` **`ffd3f815e46135f528819c36f42fa96c8e979b2257993af122f3feaf09b992d1`**.
- `BatDailyTool/review_unreviewed_queue.py` **`b7f34b4e45377270fff99dde76360f089479c7ae495207135b9cc4fbf3ba6557`**.
- Output patch normalized SHAs: pipeline **`1a2d44d14bbbfb3ed999ab990df532dc925ac4bf368daf864944dfefbbe2a116`**, queue **`d3f4e7e569748c92a0579ed872cf26fe177e62eb38b9d50f75253dd2efaebbc0`**.
- Installer copies `verified_activity.py` to BatDailyTool. Adds optional `build(root)` after Run Daily's final timeline refresh, adds a link from `Daily_Run_Reports/index.html`, and calls `build(self.root)` from ReviewQueue.rebuild after a successful human grade sync/timeline rebuild.
- Installer preserves existing `rt_audio_daily.classify_received`, XiaoRT `.rt.json`, exact stock NZ Bats model/archive controls, existing source SHA locks, installed owner GUI and current grade archive. Uses atomic writes and a verified backup ZIP under `Tool_Backups/VerifiedBatHeatmap_*/before.zip`; rollback refuses later source edits. Unknown live SHA means **STOP**, never overwrite local custom changes. Preview is read-only, repeat preview after install is idempotent.

## Verification performed (host, not owner's full history)

- 6 repeatable unit/integration tests PASS: grade eligibility vs machine labels, canonical Shed vs externally managed South, recorded dates and midnight grouping, shared-minute deduplication, observed date range gaps, NZ fall-DST real minutes, ZIP/XLSX structural output, source preservation and compatibility installer install/rollback. The test package contains exact standalone A2.2 source snapshots; tests don't touch user's live data.
- Generated XLSX was successfully re-imported/inspected with spreadsheet parser: all **four** sheet names and headers correct, actual AR4 03:10:59 example yields `20261108\\20261108_031059.bmp.data` and recorded segment certainty 100 (not inferred from grade).
- Owner's uploaded **real** `20261108_031059.bmp` + `.bmp.data` correctly produced **one grade5**, NZ time **2026-11-08 03:10:59+13:00**, duration **7.632s**, source annotation certainty **100**, and two touched real minutes across a minute boundary; only read/copy in temporary fixture.
- JavaScript extracted from generated offline HTML passed `node --check`; **NOT browser field-validated on Windows**. ZIP CRC/integrity verified.
- No attempt made to execute user's complete on-disk BatDaily scan; cannot claim accurate full-history count or field installation.

## Acceptance checks to finish with owner

1. Run standalone `Open Verified Bat Dashboard.bat` with complete Bat directory; check total grade 4/5 count against manual review summary, calendars including nights with no positives, click one reviewed file, correct local cross-midnight grouping.
2. Verify the Shed-only plot excludes imported South/Other and its underlying `index.html` JSON; verify South-only XLSX contains eligible owner-reviewed South, source-labelled and without duplicates.
3. Open each generated XLSX in actual Windows Excel; confirm all three original-format sheets, correct row count, dates and **human-grade provenance** sheet; copy rows to the owner's existing Bat spreadsheet.
4. If guarded preview finds exact A2.2 hashes, choose install; then verify Run Daily and Fast Review automatically regenerate dashboard after annotation edits, and original media/backup hashes remain unchanged. If mismatch, retain standalone use and merge against owner current sources.
5. Validate XLSX/HTML file links and case-sensitivity on Windows file:// URLs, multiple recorders and daylight saving, performance over entire calendar collection.

**Open limitations:** Unknown true recorder coverage and independent bat encounters; uncertain species; no end-to-end Windows verification; external noncanonical Shed reconciliation and future reference FLAC corpus remain separate; no training/firmware changes. Do not close #25 or mark full #27 done without field acceptance. Full executable source ZIP must eventually be committed to repository or archived in owned Library for independent recovery.
