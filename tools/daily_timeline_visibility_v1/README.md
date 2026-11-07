# Daily Timeline candidate visibility fix v1, 7 November 2026

Extract this folder and run `Install and Rebuild.bat` with Daily Run closed. It locates Documents/Bat by default, checks the installed timeline against the uploaded source, backs up replaced scripts, and rebuilds all timelines from existing recordings/annotations. Future Daily Runs already invoke this renderer at the start and end, so no daily_pipeline.py replacement is necessary.

## Implemented

- Separate counts and hollow purple diamond markers for recordings whose saved annotations contain AviaNZ bat candidate labels.
- Candidate tooltips include recording ID, time and annotation classification. Click a candidate to open the original recording.
- Existing human grades remain separate and retain the existing provenance gate.
- Review-state counts and UTC report-generation time are visible. A night with no accepted reviews gets an explicit diagnostic.
- Report-only rebuilding does not run recognition, edit sidecars, upload firmware or alter model labels.

## Diagnosis and remaining work

The uploaded 20261106 timeline contains 1040 AR4 recordings, 421 SD recordings, 244 recordings with bat candidate annotations, four RT candidates and 182 RT health records. All 1461 AR4/SD rows are marked unreviewed. The old headline and chart markers represented only human review, hiding the machine candidate count in the table. The daily pipeline already refreshes at both ends of a run; reviews made after that run require rebuilding.

This fixes machine candidate visibility, not the unproven cause of missing manual grades. The supplied BMP contains the spectrogram, not the review metadata. The original .bmp.data companion and its folder path are still required to establish whether the review was saved elsewhere, not saved, overwritten or excluded by the metadata policy. Do not relax the human-review gate or relabel machine candidates as confirmed bats.

The RT candidates occur during the afternoon. The collection metadata says complete=false. No conclusion about overnight detection sensitivity follows from these four records. RT logs and timestamps are not altered by this patch.

The installer accepts only the exact uploaded timeline or this patched version. Other updates are preserved by stopping on a mismatch. If needed, restore the backed-up Python files from BatDailyTool/Timeline_Backups.
