# Bat recognition training: versioned baseline models

**Status: candidate/development only. No firmware or AviaNZ model replacement.** The `training/` subtree is public source/metadata for agents and contributors, **not** a repository for private bat recordings or reviewer annotations.

## Initial baseline (trained 2026-11-05 NZDT)

`phase1/train_baseline_models.py` is the exact training and feature-extraction source uploaded by the project owner (source SHA-256 `27ea228bb979c6bd3de4ff653f3f3ee0e800c033460e3aa7e0c3951eb8eee923`). The original labels, WAVs/BMPs, .data sidecars, local absolute paths and frozen night split file are **not** included here. Both models use 165 features: 32 bands × 5 robust temporal statistics plus five global features, a `StandardScaler` and balanced `LogisticRegression`. The desktop-only WAV branch uses an 8–45 kHz common band.

| Model | SHA-256 (original joblib) | Test TP | FN | FP | TN | Interpretation |
|---|---|---:|---:|---:|---:|---|
| BMP v0.1 | `4f92db5888798a2bd865d91c3b1f184d92086991229abc18a49ba0ec8a34519b` | 14 | 2 | 59 | 624 | first desktop second-opinion candidate |
| WAV v0.1 | `c63c748334315bf243d1dd3013d19834299b235ea375c676ba534eb291e72ae9` | 8 | 1 | 2 | 662 | preliminary XiaoRT shadow candidate |

These numbers are **recording-level** accuracy, not pulse-level detection sensitivity. The WAV held-out set contains just **9 positive recordings**; both benchmarks require independent night validation, reviewed disagreements, and in-field tests. Neither model is an AviaNZ `.h5` CNN or an executable ESP32 model.

## Source-of-truth files

- `phase1/train_baseline_models.py`: exact user-provided training source.
- `phase1/reports/{bmp,wav}_model_report.json`: versioned run metrics, thresholds, split/manifest hashes.
- `phase1/model_registry.json`: filenames, checksums, statuses, compatibility and promotion policies.
- `phase1/models/{bmp,wav}_v0.1.joblib`: **not committed yet**. The owner-supplied binary artifacts have been SHA-checked against the reports, and a separate local publisher will place them here without renaming any earlier version. Until those files are actually on GitHub, the registry's `artifact_committed=false` remains accurate.

## Daily retraining (planned, not currently automatic)

Bat Daily v1.9.5 currently imports recordings, runs the control AviaNZ CLI, captures human Fast Review grades and writes `Review_Training/review_inventory.csv`. The independent Phase1 audit and `TrainingWorkbench/train_baseline_models.py` still require separate commands. There is **no** reliable automatic training or GitHub model publication in the current Daily Run. Implement as a *separate failure-isolated post-review step* after Bat Daily has fully completed, verified current recordings and cleared its lock:

1. Reconcile imports and annotation evidence, never infer review completion from machine predictions.
2. Compare the current hash-bound set of eligible human-graded examples against the last *trained* registry snapshot. Count **new positive and negative evidence and new recording nights**, not just raw files.
3. Use configurable thresholds (e.g. **10 new reviewed positives or 200 new hard negatives**, at least one new night; defaults require field validation). When below threshold, record `no_new_training`, not a failure.
4. Snapshot inputs with SHA-256 and preserve `night_splits.json`; never leak held-out nights into training.
5. Train to a **new** model version, compare validation performance/false positives with champion, archive frozen test results separately; record dataset hashes and code/library versions.
6. Publish immutable **candidate** binaries, manifest and reports to a protected Git branch/PR using configured Git credentials. If GitHub is unreachable, preserve local candidate for retry. Never block Daily Run or lose a review due to publication failure.
7. Require human approval plus multi-night XiaoRT/SD shadow testing before `approved`, `active` or `rollback` manifest pointers change.

## Future model-only Wi-Fi updates

Neither the archived RT `NZRT-FIELD-PILOT-5-WIFI-2-JOURNAL` snapshot nor the current XiaoSD firmware implements secure, versioned model-only OTA deployment. Add this only when both devices have a validated embedded feature extractor/inference runtime. Recommended design: separate `candidate`, `shadow`, `active` and `rollback` slots; signed manifest pinned to firmware/runtime feature schema; HTTPS download to inactive partition/file; verify model SHA-256, signature and memory limits; atomic activation; rollback after boot/inference failure. Shadow may **not** suppress current recording triggers. Never download/run Python pickle on the ESP32. Keep XiaoSD unchanged until RT shadow mode has field validation.

## Operational caution

The current Bat Daily launcher can leave a stale `.bat_daily_tool.lock` after interruption. The review summary scans canonical `YYYYMMDD/AR4YYYYMMDD` and `YYYYMMDD/XiaoYYYYMMDD` folders, not arbitrary review queue copies. Recent Win11 field reports show grade counts increasing but missing recent-night folder completion after lock error. Reconcile those issues before enabling any automatic model build. See [issue #13](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/13) and [training issue #14](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/14).

All future changes must update this README, the registry and the relevant GitHub issue with exact implementation state, not merely intended work.
