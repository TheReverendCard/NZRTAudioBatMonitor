# JOURNAL-4 fail-open source candidate (10 Nov 2026)

**Status: exact-source, host-tested candidate. NOT COMPILED FOR OR FLASHED TO ESP32-S3.**

## Why

Owner's installed `NZRT-MLP-1-JOURNAL-3` was confirmed by field status and a private 6 November `receipt.json`.  Owner supplied `RT_Journal3_Source_For_Review.zip`. All **six** relevant sources had SHA256 matching that receipt, including `WildlifeJournal.h=84e4ffc89d65615ccd07922fd9c0e9e9b64f0054e67a29c5136283adacdb050c`. No need to continue guessing against the older JOURNAL-2 PR #24 implementation.

Observed error on 10 November: repeated `tail_read` and `reader_scan_read file=/packet_log offset=259135`, resulting in `JOURNAL-3 fault=1 verified=0`, interrupted fresh journal writes and no recent daily snapshot. The user retained an 8 MiB verified flash image before attempting any changes and considers historical record recovery sufficient. Priority is **live working detector**, not lossless preservation of old redundant journal records.

## Candidate changes against exact JOURNAL-3

1. `WildlifeJournal.h`: unreadable active tail or size isolates only `/packet_log` to `/packet_log.bad`, falling back to deleting only `/packet_log` when rename fails and owner-approved retention loss is necessary. No SPIFFS format; never erase MeshCore identity, WiFi credentials, NVS or model slots. A failed write/readback schedules recovery; unsuccessful recovery backs off for 30s instead of hammering SPIFFS. Interrupted rotation conflict discards stale pending journal, not newer active segment. Diagnostic counters report quarantine/discard/cooldown/read fault.
2. `WildlifeJournal::Reader`: scans each archive before export; skips an unreadable old segment, preserving newer good records. Continues to refuse a midstream read failure. Retains warnings for skipped data.
3. `WildlifeUpload.h`: does not treat a historical archive-read fault as a permanent veto on subsequent fresh verified journal exports. Existing token, protocol, FNV checksum, receiver endpoint, daytime schedule and HTTP ACK contract remain unchanged.
4. `WildlifeMic.cpp`: retain new acoustic event records when its bounded 64-entry pending journal buffer fills, discarding only the oldest RAM-staged metadata and incrementing `ram_dropped_oldest`. USB candidate lines remain immediate; repeated journal-failure messages throttled. Build header updated to `NZRT-MLP-1-JOURNAL-4`. Original microphone and DSP processing and MLP source are unchanged.

## Reproducibility and artifact limitation

The tested three patched source files, unified diffs, Python source-update preview/backup/restore tool, C++ mock SPIFFS fixture/tests, README and manifest are packed in **`NZRT_Journal4_Failopen_Source_Patch_20261110.zip`** provided privately in the 10 Nov ChatGPT conversation. ZIP SHA256: `243add1273ea7120804900f2f7e8069421431c237433266854fe319d0784133e`. `PATCH_MANIFEST.json` is committed on this branch with exact source SHA256 pairs. **The source ZIP itself and the actual full patched source are not yet stored in this GitHub branch.** Do not treat this branch alone as buildable or use it for flashing. Retain source ZIP in the Bat recovery directory and add the exact source after appropriate code review.

Host validation: 24 C++ checks using mocked Arduino SPIFFS/Print/Stream, including read/seek failures, mid-file read failure at offset 259135, rename and delete failures, 30s cooldown, new active after quarantine, retained identity, low-space reclaim, streaming healthy archives and interrupted rotation. Additional Python source updater tests: preview, apply, idempotent reapply, hash-guarded restore, refuse modified local source. Integration source assertions confirm current firmware identity, no SPIFFS formatting, no permanent readFault upload veto and bounded pending RAM policy. **No ESP32 PlatformIO build, hardware test, end-to-end receiver ACK or acoustic/DSP runtime regression has been done.**

## Safe next steps

- Extract ZIP to `C:\Users\revje\Documents\Bat\RT_Recovery\20261110`. Verify ZIP hash. Run `py -3 .\apply_journal4_source.py` for read-only preview against owner's local project. Do not attempt Flash/Update RT yet.
- During a controlled daytime maintenance session, apply source only with `--apply` (backups recorded); build with the owner's already configured PlatformIO `NZRT_Xiao_S3_WIO_wildlife_repeater` target. Preserve rollback binary and original full-flash backup.
- Before flashing, test a fresh build's serial commands, WiFi control/receiver compatibility and failure injection on a spare or recoverable device, plus hard limits on detection/dropouts and uptime. The prior 17.5s MLP synthetic test and high DSP-overrun counters remain separate unresolved performance issues.
- After field installation verify `JOURNAL-4` status, fresh append `verified` increments, no repeated tail_read, current candidate stream and daytime snapshot receipt; monitor 2+ nights.

Related: GitHub issue #27, PR #24 JOURNAL-2 prior base, docs/RT_JOURNAL3_PROVENANCE_AND_FAILOPEN_20261110.md.
