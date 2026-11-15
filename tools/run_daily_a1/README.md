# Bat Daily, Release A1 candidate, 7 November 2026

This is a staged subset of #27, prepared from the owner's uploaded pipeline, annotation manager and known queue package. It is not the whole roadmap. No field installation, full Windows Daily Run, GUI, firmware or model deployment has been verified by this release.

## Use and rollback

Close Run Daily and Fast AviaNZ. Extract the entire package. Double-click **Preview Update.bat** for a dry run, then **Backup and Install.bat**. Default Bat root is Documents/Bat; an alternate location is supported by running the batch with `--root "D:\Bat"`. Run the normal Review All Unreviewed and Run Daily Scan launchers afterwards. Existing launcher scripts and settings are preserved. The launchers must invoke the patched Python modules; if the Windows launch sequence bypasses them, the new messages will not appear.

Before changing scripts the installer writes a SHA-256 verified pre-update ZIP under Bat/Tool_Backups/RunDaily_<UTC>/before.zip. Includes the BatDailyTool directory (including settings and nested files, excluding .venv, .git and __pycache__) and top-level Bat launcher scripts. Contains local settings: keep private. It is a tool backup, not a backup of recordings, models or the entire Bat drive. On version mismatch it stops after backup instead of replacing an unknown hotfix. To undo this installation, run Restore Previous Scripts.bat and paste that installation's before.zip path. Restore verifies prior contents and refuses to overwrite subsequently edited code. Rebuilding derived HTML after rollback remains optional.

## Findings and changes

- A saved grade 5 was parsed correctly while the older generated timeline recorded the same recording as unreviewed. Rebuilding restored visible marks in the field. The saved JSON cannot tell us the exact order of Windows GUI saves and report generation. A definite integration gap exists: the Fast Review queue previously synchronised grades without triggering report rebuilding. It now rebuilds timelines after successful queue reconciliation. Reviews made directly in another AviaNZ window still need the usual report rebuild.
- The earlier nightly index omitted saved AviaNZ candidate counts. The v1 visibility overlay is included. Purple diamonds read current annotation species labels. They are not immutable stock-model prediction evidence.
- The pipeline previously changed files before acquiring its single-instance lock. Patched pipeline and queue now take an exclusive shared lock before their operations, with PID, host, action, UTC and ownership token. A crash leaves evidence for existing manual stale-lock recovery. No automatic deletion of another run's lock.
- Next-night folders are created once a valid target is known, independently of AviaNZ success. A final timeline exception now propagates as a partial/needs-attention outcome. Earlier setup failures do not claim a scanned backlog.
- Receipt generation repeatedly enumerated the same Backup folder once per BMP. Enumerate once per distinct folder, retaining exactly the same file set.
- A pre-existing machine backup was formerly accepted without verifying its provenance receipt. New publication uses a complete temporary file plus exclusive NTFS link. An existing missing/mismatched manifest entry or changed media/backup bytes requires investigation. Preserve the original; never reconstruct historical machine evidence from an edited sidecar.
- Queue separates accepted explicit 1–5 hotkey grades, historical empty reviewer/ledger-marked cases needing identity resolution, and ordinary unreviewed recordings. A receipt- and BMP-hash-verified before/after deletion of original Don't Know segments with accepted human handling is excluded from repeat grading. This exception does not assign a new automated training label. Untouched slots can be reprioritised; unsynced modified staged files are retained. Priority is reflected in names of newly staged links and in the first file opened. Preserve originals and archive exact old review bytes; checksum and conflict checks run on publication.
- Both Python entry points report configured-source backlog totals separately from staged subset. Review shows counts before/after, sync progress and conflicts. Daily reports after processing and at the end. See Daily_Run_Reports/FastReviewQueue/backlog.json. Partial/unknown inventories must not be interpreted as global zeros.
- External Data intake starts with a separate read-only BMP inventory for the three registered roots. It records relative aliases, card date, size, mtime, hash and last-seen time in SQLite. Two unchanged observations at least five seconds apart precede hashing. No external media/sidecars are published to the working review queue, Shed timeline or model. This is an inventory stage, not yet classification, external Shed promotion or a licence decision. Existing review backlog is labelled partial when External Data exists.

## Roadmap audit and release gates

| Issues | Current status / outstanding work |
|---|---|
| #12, #13, #27 | Above fixes prepared. Still need Windows launcher end-to-end, full hash-bound conflict/provenance reconciliation, restartable stage receipts, external identity-aware queue counts and direct-GUI exit refresh. Editing a live sidecar can still invalidate an earlier machine receipt; keep standalone report rebuild for review-only changes. Original RT archive completeness remains a separate concern. |
| #26, #19, #20 | Inventory only. Canonical Shed alias merge, date/clock attribution, classified external working views, separate South/Other review/training, permissions/licensing for reference WAV/FLAC and optional South spreadsheet export pending. Raw sources remain unchanged. |
| #21 | Fast Review display controls are separate GUI work; no GUI files patched. |
| #25 | Verified activity heat map/search and coverage-aware union minutes pending (Release B). |
| #14, #22, #23 | Training snapshot reconciliation, grouped evaluation and candidate-model work remain separate. |
| #16, #24 | RT firmware/logging is a separate track; Daily ingestion of RT MLP records/audio and accurate overnight coverage still pending. |
| #12, #17, #27 | Acoustic clock alignment and controlled model deployment deferred to the documented Release C gates. |

## Verification and next Windows check

Host fixtures exercised 1,000 ordinary + 75 ambiguous, first 150 staging, 75 grade-3 retirements, conflict preservation, exclusive lock ownership, read-only external inventory with duplicate content across two paths, verified backup, compatible/no-op upgrade, refusal of a modified script, and rollback. Real Windows batch launch, AviaNZ GUI/hardware, and all external-site acceptance tests are not claimed. To finish integration collect the installed Run Daily Scan.bat, Review All Unreviewed.bat, review_dataset.py, fast_review_entrypoint.py and any version-mismatched scripts. Do not share the entire private backup. Where known launcher versions differ, integrate their own pre/post hooks instead of overwriting them.
