# Provisional RT missing-night Daily drop-in, 2026-11-10

Owner explicitly requested easiest recovery: repair the carved CSV into the existing `XiaoRT_Logs/Raw` file format so the regular Daily can be rerun without extensive forensic reconstruction. No owner-local files have been altered.

Created conversation artifact `RT_Daily_DropIn_20261109.zip` with:
- `capture_20261110T000000Z_20261109_rt_recovered.txt` (590 distinct RT candidate lines, session 5EB1281B, run 4, night Nov 9/10 NZDT)
- same stem `.json` manifest, bytes and SHA256 verified: `7b9339b0557a3124412273b13b1f7370e5703317e5eb8cb0e7cefd9e72011599`
- `restored_vs_original.csv` with original carved partial line and synthetic/retained fields
- `README.txt` with additive installation instructions

The lines imitate the original `NZRT CANDIDATE` syntax. Preserve each valid parsed original field; fill missing damaged fields with neutral placeholders including `score=0`, `class=uncertain`, `peak=0.00x` and zero numeric pulse/frequency fields. In this batch 340 scores, 385 classes and 211 peaks were filled synthetically. **Do not interpret neutral placeholder scores as real measured values or use the package as performance/training truth.** Mark all `unverified=1 recovered_flash=1 recovered_partial=1`. This is deliberately approximate, for activity timeline only. Session/run/seq and UTC timestamps are grounded in the raw flash carve.

Recommended user placement: copy **only** new paired .txt/.json into `C:\Users\revje\Documents\Bat\XiaoRT_Logs\Raw`, without overwriting existing snapshots, human reviews, or generated index; rerun night 20261109 with normal Bat Daily. Parser implementation is NOT available in connected GitHub repository, so success in original `index.html` has not been verified. If Daily skips these files because Raw is not scanned as input, or filters synthetic classes, inspect exact installed importer and adapt a recovered-event branch; do not overwrite originals.

RT firmware reliability remains top priority: bound journal tail errors, fail-open capture, preserve runtime service, separate live event metadata from journal/WAV, investigate ML 17.5s/2s audio processing cost. Exact deployed JOURNAL-3 source still needed for safe patch. Raw flash preserved privately. No firmware update performed.