# Source provenance preflight for the deployed JOURNAL-3 RT

This branch is **NOT READY TO FLASH** and must not be used to update the owner device.

### Discovery
The owner previously installed `NZRT-MLP-1-JOURNAL-3` on 6 Nov 2026 from `RT_Journal3_Recovery_Patch_v1.zip`; the installation receipt was recovered from their private file history on 10 Nov.

The exact installed `nzrt/WildlifeJournal.h` SHA256 is `84e4ffc89d65615ccd07922fd9c0e9e9b64f0054e67a29c5136283adacdb050c`. The installed `nzrt/WildlifeMic.cpp` SHA256 is `1fe75d81d5f0aa9fc9249a50fc9214188a5b54ed2bd60b89596b3d9b15656b7f`. Those **differ** from the earlier JOURNAL-2 content in the GitHub baseline and MLP PR #24.

### Current state
- The newly drafted `rt_mlp_update/payload/nzrt/WildlifeJournal.h` is an exploratory **JOURNAL-2-based prototype**, not proven to represent the owner's JOURNAL-3 implementation or reproduce its error-handling semantics.
- No confirmed JOURNAL-3 source patch, build, device flash, or test is completed by this branch.
- Never run the generic `Update RT.bat` using this branch's payload.
- The failed journal, event RAM backlog, live event delivery and upload reader are all related; a fix limited to the old Journal.h is not sufficient.

### Source collection step
Run `tools/RT_Journal3_Source_Preflight_20261110.py` on the owner's **local installed project**. It reads only six C++ files, compares their hashes to the 6 Nov field receipt, and makes a review ZIP outside the project. The ZIP should be manually inspected for secrets before sharing. The script does not modify firmware, erase SPIFFS or connect to hardware.

### Next release gate
Only after the exact deployed source is obtained, port the bounded-error recovery to that source, add fail-open pending-event handling, verify explicit journal segment reinit and recovery under injected I/O faults, run a full owner-side PlatformIO build and test on hardware. Keep rollback binary and pre-repair SPIFFS image.

Canonical provenance is [docs/RT_JOURNAL3_PROVENANCE_AND_FAILOPEN_20261110.md](../../../../docs/RT_JOURNAL3_PROVENANCE_AND_FAILOPEN_20261110.md) on main.
