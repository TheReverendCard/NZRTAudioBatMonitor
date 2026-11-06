# XiaoRT reconstruction status

Updated 6 November 2026.  Last supported field identity: `NZRT-FIELD-PILOT-5-WIFI-2-JOURNAL`.  Fresh owner-supplied COM8 status on 6 November confirms this build identifier; not a binary-to-source identity claim.

## Evidence

PR #16 contains eleven source files recovered from the owner's November 5 snapshot.  On November 6 this chat independently compared Git blob hashes for all eleven against its retained `wifi_work/compile_project` workspace: all eleven match exactly.  PR #16 remains a draft, based on PR #11.  Main is not the recovered field release.

That same retained build workspace contains the previously omitted `WildlifeTime.cpp`.  It is now archived separately in `recovery_candidates/WildlifeTime.cpp`, not substituted into the owner's original snapshot.  SHA-256: `577fb7425ce2d2e688a9b12a673f250decf481c119d4a9f45c5ab81d729eabd5`.  It integrates the JOURNAL-2 writer and WildlifeUpload tick.  Reviewed source contains NVS credential access, not embedded WiFi credentials.  This is a strong reconstruction candidate, not proof of the owner's compiled source.

## Reconstructed capabilities

- FieldPilot-5 audio pipeline and RT-SCORE-1 heuristic shadow scoring, not a trained MLP/CNN.
- Rolling, read-back verified JOURNAL-2 flash journal, journal health/test commands, no automatic format on filesystem mount failure.
- Serial log dump/erase and more robust line handling.
- Daytime microphone/DSP standby with MeshCore still running; not the SD recorder's deep-sleep firmware.
- Daytime authenticated `/rt-log` snapshots, checked response body/hash, retained local journal.  First attempt after 60 seconds of standby, hourly after success, 15-minute retry after failure.  Fresh verified journal required before upload.
- Candidate recovered time module: boot NTP plus 24-hour attempts, authenticated MeshCore clock integration.  Adaptive drift-based intervals are not implemented here.

## Not established as deployed

Learned MLP/CNN, INT8/SIMD model inference, model OTA, live nighttime WiFi alerts, SD recording/fallback changes and all proposed future changes must not be inferred from this RT build string.  A separately prepared shadow port is not deployment evidence.

## Finish the reproducible release

1. Obtain fresh `nzrt status`, `nzrt journal`, `nzrt time` and `nzrt day` output.  Preserve logs before any update; no erase is needed.
2. Recover the owner's complete project configuration: platformio.ini, additional referenced INIs, partition CSV, build scripts, upstream commit/dirty patch and resolved dependency versions.  Retain firmware.bin and build metadata if available.  Keep credentials, receiver token, NVS and device identity material private.
3. Compare the candidate time module against the owner's copy.  Reconstruct the pinned upstream checkout and overlay all recovered modules.  Resolve HTTPClient dependency explicitly in the target build.
4. Build, verify journal retention/readback and upload acknowledgement, schedule wake, capture/DSP health and MeshCore coexistence.  Archive a rollback binary before adding a learned model.
5. Publish one canonical RT release with source commit, dependency pins, binary SHA-256, target/partition profile and separate model ID.  Use an updater with source/binary checks and a manifest rather than inferring a project from the newest Downloads folder.

No new firmware built or flashed by this reconstruction update.  Source and documentation recovery only.  See PRs #11, #15 and #16.

## Owner upload comparison, 6 November

The owner's live `nzrt/WildlifeTime.cpp` from `C:\Users\revje\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor` exactly matches the candidate SHA-256 above.  The previously missing time source is now independently corroborated.  Both uploaded root platformio.ini files are byte-identical (SHA-256 `994e3af4321a30a502ffb5c4a61725adbddaabd5f89fcfff8c889ff9fc43bddc`), despite different file dates.  They include `platformio.local.ini` and `variants/*/platformio.ini`; the root files alone do not define the wildlife build target.

The four uploaded WildlifeMic/Detector .cpp/.h files from Downloads differ from the recovered snapshot.  The uploaded microphone implementation lacks the JOURNAL-2 and RT-SCORE-1 identifiers seen on the live device.  Do not overwrite recovered source with these older Downloads files.  Use the NZRTAudioBatMonitor-meshcore project as the next configuration recovery source; request its `platformio.local.ini` to resolve the custom target and its inherited board configuration.

Live session 4717F833: JOURNAL-2 fault=0, errors=0, verified=6; WIFI_NTP synced; daytime AUTO standby; WiFi log ACK.  Startup DSP drops=38 and input gaps=15 remain observed; healthy journal does not establish lossless audio acquisition.

## Custom target recovered

Owner supplied `platformio.local.ini`, now archived in recovery_candidates.  It defines `NZRT_Xiao_S3_WIO_wildlife_repeater`, inherits `env:Xiao_S3_WIO_repeater`, compiles WildlifeMic/Detector/Time/Day and explicitly adds HTTPClient and WiFiClientSecure.  It sets LoRa coding rate 5 and TX power 10, unsetting TX power 22.  Relative to this chat's retained compilation workspace, the only textual difference is WiFiClientSecure's position in lib_deps.  Preserve the owner's order until verified by a fresh build.

The inherited target is located in `variants/xiao_s3_wio/platformio.ini` in the retained workspace.  The owner's copy of that file has not yet been compared.  It can contain the MeshCore ADMIN_PASSWORD build flag; redact actual passwords before sharing.  Root and local INIs are now recovered, but full build reproducibility and binary matching remain unverified.  The available Python runtime initially had no PlatformIO installation; installing build tools is not evidence of a successful firmware compile.

## Board configuration verified against owner upload

The owner supplied variants/xiao_s3_wio/platformio.ini on 6 November (uploaded as platformio(2).ini).  Comparison against the retained workspace is identical after replacing ADMIN_PASSWORD lines in both with a sentinel.  Full file bytes differ; no assertion is made about the actual password values.  All other board configuration text, including pin assignments and inherited build settings, matches.  A credential-redacted evidence copy is archived under recovery_candidates/variants/xiao_s3_wio/platformio.ini.redacted; it is not a ready-to-build config.

This closes the requested root/local/board INI collection and confirms the time module.  No more individual INI uploads are needed for this comparison.  Remaining work is assemble and compile the reproducible project with resolved dependency versions, preserve local private configuration, verify hardware behavior and retain rollback.  No successful fresh compile or binary-to-device match has been established.  On the previous attempt PlatformIO itself installed, but the platform installation was stopped before compilation; no firmware was generated by that attempt.
