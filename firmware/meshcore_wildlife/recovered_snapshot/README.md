# Recovered local XiaoRT source snapshot, 5 November 2026

**Review-only, incomplete as a standalone firmware build. Not a device upload.**

This branch is based on the existing experimental MeshCore firmware development line (`exp/meshcore-wildlife-repeater`, draft PR #11) and does not overwrite it. The recovery source originates from the user's read-only local project collection, `RT_Source_Recovery_20261105T080436Z.zip` (collected 2026-11-05 08:04:36 UTC, local Git HEAD `ec387c02edb488b94f717bd7f62543ea35d7a444`).

## Confirmed source evidence

The recovered `nzrt/WildlifeMic.cpp` and `nzrt/WildlifeUpload.h` identify build `NZRT-FIELD-PILOT-5-WIFI-2-JOURNAL` and implement `JOURNAL-2` with a read-back verified journal, segmented/retained flash logs, telemetry and `/rt-log` delivery. These match the *build identifier* of the owner's previously observed device status, but no binary-to-source verification or fresh device query was performed. Recovery contains eleven files (including `examples/simple_repeater/main.cpp`), and all their SHA-256 hashes were verified against the archive's `snapshot_manifest.json`.

**The source collector intentionally excluded `nzrt/WildlifeTime.cpp` and `nzrt/WildlifeUploadConfig.h`.** These files must not be inferred or invented. `WildlifeUploadConfig.h` contains private receiver configuration and must never be committed. The full local PlatformIO tree, pinned dependencies, currently flashed binary and full build report are not provided in this snapshot.

## Recoverable source paths

The original relative source paths are maintained under `firmware/meshcore_wildlife/recovered_snapshot/` to avoid overwriting older experimental source on this branch. These are for review and comparison, *not automatically compiled*. Expected contents and hashes are documented in PR #15's `firmware/rt_provenance/release_manifest.json`.

| Snapshot path | Purpose |
|---|---|
| `nzrt/WildlifeJournal.h` | Full recovered rolling/read-back verified `JOURNAL-2` implementation |
| `nzrt/WildlifeMic.cpp` | Build identifier, audio pipeline, scored candidates and journal writes |
| `nzrt/WildlifeUpload.h` | Daytime Wi-Fi journal snapshot, firmware header, retry logic |
| `nzrt/WildlifeDay.cpp` | Wake/standby lifecycle and journal records |
| `nzrt/WildlifeDetector.cpp`, `nzrt/WildlifeScoring.h` | 192 kHz RT pipeline and RT-SCORE-1; hashes match the earlier FieldPilot_5 release |
| `nzrt/WildlifeDay.h`, `nzrt/WildlifeDetector.h`, `nzrt/WildlifeMic.h`, `nzrt/WildlifeTime.h` | Corresponding headers |
| `examples/simple_repeater/main.cpp` | Local repeater setup, journal command dispatch and CLI |

A verified copy of `WildlifeJournal.h` was committed first. The remaining snapshot files need to be imported from the exact recovered archive and compared with their manifest checksums before this source PR is ready for review. **Do not merge this branch or call it current flash source until all source, build and test checks pass.**

## Shadow-mode next steps

1. Confirm the currently flashed `nzrt status` and the source-checksum provenance.
2. Import every recovered, checked source file without any credential material.
3. Reconstruct a reproducible full PlatformIO build and test `JOURNAL-2` / RT Wi-Fi logs unchanged.
4. Add the WAV logistic-regression model and *identical* 8–45 kHz feature extraction behind an opt-in shadow flag, preserving RT-SCORE-1 and existing trigger.
5. Include model ID/threshold, score and timing in journaled `NZRT ML_HIT` entries and Wi-Fi snapshots. Deploy only after host-device feature agreement and processing-overrun benchmarks.
6. Keep XiaoSD firmware unchanged.

Related: [PR #11](https://github.com/TheReverendCard/NZRTAudioBatMonitor/pull/11), [PR #15](https://github.com/TheReverendCard/NZRTAudioBatMonitor/pull/15), [training issue #14](https://github.com/TheReverendCard/NZRTAudioBatMonitor/issues/14).
