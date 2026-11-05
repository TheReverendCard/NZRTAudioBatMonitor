# XiaoRT firmware release ledger and source-of-truth policy

**Last reconciled: 2026-11-05 NZDT.** This document distinguishes the *last build actually reported by a device* from the *latest source code recoverable in GitHub*. Those are currently **not the same**. Do not promote a candidate to "flashed" merely because a ZIP was created or an updater compiled.

## Current status

- **Last observed running RT build:** `NZRT-FIELD-PILOT-5-WIFI-2-JOURNAL`, reported in the user's 2026-11-01 `nzrt status`/journal diagnostics and subsequent Wi-Fi snapshot metadata. Journal reports `JOURNAL-2`, `fault=0`, `errors=0`, and `NZRT JOURNAL_TEST result=PASS` in the local bench test. The precise current flash state **after** this observation has not been independently re-read.
- **Last source packages in hand:** `NZRT_RT_FieldPilot_5` (dated 2026-10-28) and `NZRT_WiFi_Daily_Update` (dated 2026-10-30/31). Their SHA-256 is recorded in [the release manifest](../firmware/rt_provenance/release_manifest.json). They **predate** JOURNAL-2 and cannot safely be called the latest firmware. They are not installed as source on `main`.
- **Missing source to recover:** the `RT_Logging_Update` package/project changes delivered around 2026-11-01. It added a bounded rolling journal, write/read-back validation, fault counters, a manual `nzrt journal test`, terminal fixes, and protection from automatic formatting. Until its code is recovered, the repository cannot rebuild the newest *observed* device release.
- **GitHub source status:** `main` has commissioning documentation. Open draft PR **#11**, branch `exp/meshcore-wildlife-repeater`, contains earlier experimental MeshCore wildlife C++ modules and docs; it is **not** a certified mirror of the flashed firmware. PRs #8 and #10 are other experimental lines. Do not replace collaborators' branches or merge unverified firmware silently.
- **Trained classifier status:** first WAV and BMP `sklearn` logistic-regression baselines were trained separately on 2026-11-05; there is **no** deployed on-device learned classifier yet. `RT-SCORE-1` in the field is the older hand-scored, shadow-mode heuristic, not the trained WAV model. See issue **#14**.

## Chronology and what we can substantiate

| Date (NZ) | Identifier | What changed | Evidence/limitations |
|---|---|---|---|
| 2026-10-28 | `NZRT-FIELD-PILOT-5` | 192 kHz PCM and `RT-SCORE-1` scored, retained candidates; native and module compilation tests | FieldPilot_5 ZIP contains C++ source overlay, patch, updater and validation. Source was **not** pushed by that release. |
| 2026-10-30/31 | `NZRT-FIELD-PILOT-5-WIFI-1` | Daytime Wi-Fi journal snapshots, `WildlifeUpload.h`, receiver and Daily Run integration | WiFi_Daily_Update ZIP contains updater and upload header, not a full independently versioned project. Host tests passed; its documented clean full compile was blocked by toolchain download verification. Subsequent logs have shown this build. |
| 2026-11-01 | `NZRT-FIELD-PILOT-5-WIFI-2-JOURNAL` | `JOURNAL-2` rolling/verified journal and integrity checks | User-observed status and snapshot receipt verify a **running device build**. The complete matching source package has **not yet been recovered or committed**. |

**Caution:** the ZIP file modification dates and validation records do not prove a particular build was flashed. Preserve serial `nzrt status` identity, log snapshot headers, and source SHA/build commit together before declaring a release complete.

## Recovering the current deployed source

The existing user's local PlatformIO project has historically been:

`C:\Users\revje\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor`

This is a **local workspace**, not proof of an identical GitHub revision. First copy/backup the whole project locally and confirm which sources were last compiled. Check `nzrt status`, `nzrt journal test` (diagnostic; do not erase the journal), and PlatformIO build/config records. Search the user's local downloads for `RT_Logging_Update` and the corresponding updater source, plus any `nzrt_backup_wifi_*` or newer journal-update backups. Preserve the original observed build identity alongside the source snapshot.

**Never upload secrets or private config.** In particular, omit `nzrt/WildlifeUploadConfig.h` (contains receiver URL/token), `platformio.local.ini`, `receiver_config.json`, Wi-Fi passwords, private keys, local `.env` files, logs/recordings with sensitive identifiers, and binary flash/FS dumps. Inspect any other headers or diffs for embedded credentials before publication. Do not use local backed-up credentials to rebuild in CI.

After recovery, submit a **separate reviewable firmware source PR** based on PR #11's experimental lineage (or an explicitly documented new branch), containing:
1. The actual C++ module source diff from the recovered project, including `JOURNAL-2`.
2. A reproducible/pinned upstream MeshCore dependency commit. The prior FieldPilot_5 ZIP cites pinned upstream `81dbae592ffad40b4212bc0b37e82b38da08f4bc` and project base `7e8f3181844d0fee4200c8f771b4163f7d920ff9`; verify the recovered project still matches.
3. A **credential-free** build profile, build/version string, and a source commit ID or deterministic hash emitted in `nzrt status`.
4. Successful full PlatformIO build and device upload evidence plus a journal integrity result before marking flashed.
5. A changelog indicating exactly what was changed and a rollback/recovery procedure.

## Future rule: every actual RT upload has a source record

For every future RT/SD firmware upload, use a new manifest entry and GitHub commit/PR *before* flashing, or immediately after recovering an existing deployed revision. Record:

- UTC/NZ date, device role, source branch, commit, ZIP SHA (if used), pinned upstream dependencies, build identifier.
- Changed modules, feature flags, upload-script version, compiler/PlatformIO environment, build success and upload outcome.
- Device-reported build and boot reason after flash, journal integrity, drop/overflow counters, and follow-up field results.
- Explicitly whether this is **candidate**, **built**, **uploaded**, **device-verified**, **field-tested**, or **superseded**. Do not conflate the statuses.

No trained-model deployment should overwrite the confirmed `WIFI-2-JOURNAL` capabilities or touch the XiaoSD reference recorder. First learned WAV model integration must be a separate, versioned **XiaoRT shadow mode** with lossless existing candidate logging and Wi-Fi health journals retained. The device should report both model ID + threshold and the old RT-SCORE-1 independently.

Related issues: [#11](https://github.com/TheReverendCard/NZRTAudioBatMonitor/pull/11), [#13](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/13), [#14](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/14).
