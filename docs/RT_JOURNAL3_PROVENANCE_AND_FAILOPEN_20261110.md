# Installed XiaoRT JOURNAL-3 source provenance and recovery, 10 November 2026

## Current field device (verified via owner serial log and receipt)

- Device ID: `bcd3d73f1fb8` (XIAO ESP32-S3, 8 MiB flash and 8 MiB PSRAM).
- Firmware-reported identity: `NZRT-MLP-1-JOURNAL-3`.
- Installed via owner's local **RT_Journal3_Recovery_Patch_v1.zip** and `C:\Users\revje\Documents\Bat\RT_MLP_Update` on 6 Nov 2026.
- Owner field validation that day reported firmware identity, flash checksum/readback, journal and MLP worker startup. This does **not** mean an overnight fault test passed.
- Exact **build receipt** supplied by owner: `receipt.json`, `build=NZRT-MLP-1-JOURNAL-3`, build UTC `20261106T212100262655Z`, target `NZRT_Xiao_S3_WIO_wildlife_repeater`, firmware SHA-256 `f3eb32f68442e4772c8e9f6f86dc46f05047cf0d3d4f6c7638bcb02cb424bf1f`. Receipt says `flashed:false, hardware_verified:false` because it is a **pre-flash build receipt**; separate later owner installation logs constitute the field evidence.
- Install report path: `C:\Users\revje\Documents\Bat\Update_Reports\RT_MLP_20261106T213734198680Z` (owner-local).
- Current source project: `C:\Users\revje\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor`.

## Exact installed source content hashes (SHA-256, from owner build receipt)

| Source file | SHA-256 |
| --- | --- |
| `nzrt/WildlifeJournal.h` | `84e4ffc89d65615ccd07922fd9c0e9e9b64f0054e67a29c5136283adacdb050c` |
| `nzrt/WildlifeMic.cpp` | `1fe75d81d5f0aa9fc9249a50fc9214188a5b54ed2bd60b89596b3d9b15656b7f` |
| `nzrt/WildlifeUpload.h` | `cc9f57a9046553d8061e73a7198cc5e71155196cf292dfd3fa48d8a58db60ab5` |
| `nzrt/WildlifeDetector.cpp` | `fb3173f2123e35d9476b00c8db7dfb4720e3454377b3e39defdd3225cdad15bd` |
| `nzrt/WildlifeML.cpp` | `40067560cb504914c650082632010750c28a5efc13edd47b9fec73b294ef346c` |
| `examples/simple_repeater/main.cpp` | `745e4d9c5e91a9926d29d5f8b7421aae99fc66642888818b50736066420b7a0f` |

The build receipt also records RTFeatures/RTModel/ML header/model and a *private* platformio.local.ini hash. No private configuration should be uploaded to a public repository.

## Important distinction: GitHub archive is NOT yet the exact deployed JOURNAL-3 source

- PR #16: recovered JOURNAL-2 baseline and owner-source compile receipt.
- PR #24: `feature/rt-mlp-control-20261106`, code/build receipt and documentation refer to `NZRT-MLP-1-JOURNAL-2`. It is the preceding MLP implementation, not the post-install JOURNAL-3 hotfix.
- As inspected on 10 Nov, GitHub branches/PR source do not expose a `WildlifeJournal.h` whose contents have been verified against the installed JOURNAL-3 SHA above. JOURNAL-3 source is expected in the owner-local `RT_MLP_Update` patch/update workspace and/or the source project. **Retrieve and hash-match it before any production firmware modification.**
- A prototype `feature/rt-journal-failopen-20261110` branch was initially based on PR #24's older JOURNAL-2, **not fit for flash**, and cannot be treated as a JOURNAL-3 maintenance release until safely rebased/ported against the exact `84e4ffc8…` source and tested. If code hashes differ, STOP and examine rather than overwrite.

## Incident and next repair

On 10 Nov `nzrt journal`: `JOURNAL-3 fault=1 errors=44 verified=0 last_ok_uptime_ms=0 bytes=521941`; repeated `tail_read`. Serial `log` failed `reader_scan_read file=/packet_log offset=259135` then `dump_read`. MLP synthetic test PASSED but took 17.54s. The RT flash was imaged before repair (8 MiB, SHA-256 `cc74c5eaadbeb125d92110bad9b276db1a7cfda5e15beba065501e61d5f5d935`).. Historical recovery is being treated as complete by owner; do not spend time on further bit-perfect reconstruction.

The next build must:
1. Use the exact SHA-matched JOURNAL-3 sources; keep MLP, MeshCore, NVS identity, board config, receiver protocol and daylight behaviour intact.
2. Detect file-tail/readback errors with bounded retries, isolate or rotate corrupt journal file without indefinite retry, prefer recent activity over old redundant snapshots, and never erase non-journal SPIFFS files or private credentials.
3. Keep the DSP/event queue draining through flash failure; account for intentionally dropped old pending metadata, always report detector activity over Serial or independent live event channel.
4. Check how WiFi journal reader and journal health block daytime exports; a single corrupt archived segment should not block exporting newer healthy segments.
5. Test normal, injected corruption, full filesystem, WiFi down, power cycle, and high candidate rate before hardware installation. Record new source/build hashes and rollback binary.

**No JOURNAL-3 firmware patch or flash is yet verified as deployed by this 10 Nov work.**
