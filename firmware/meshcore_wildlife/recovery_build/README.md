# RT recovery build helper

6 November 2026.  Compile-only recovery helper; not an updater or a production release.

Download all three sibling files (verify_and_build.py, expected_sources.json, Verify and Build RT.bat) into one folder.  Run the BAT on the owner's Windows PC with Python and PlatformIO installed.  Default project is %USERPROFILE%\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor.  For another location run `py verify_and_build.py "PROJECT_PATH"`.

The helper verifies 12 recovered C++/header files plus both root INIs, then compiles the known target.  It refuses missing or mismatched files; do not bypass by regenerating the expected hashes.  It never uploads, erases or opens serial.  Verification does not yet cover the whole upstream checkout or all dependencies.  Exact bytes are required, including line endings.  Mismatches require inspection, not overwriting private config.

Receipts under RT_Build_Receipts contain compiler output, resolved package listing, PlatformIO version, source hashes and a firmware copy/hash on success.  Keep receipts private because logs and binaries can embed configuration.  Copying firmware does not itself provide a complete flash rollback; preserve partition layout, bootloader and private NVS separately before a future upload.

Verification tests: matched 14-file fixture accepted; modified time module refused; retained workspace's different dependency ordering correctly refused.  Python syntax check passed.  No new hardware test or successful full firmware compile is claimed here.

## Required for future RT releases

- One canonical release directory and tagged source commit; no newest-Downloads inference.
- Record all source changes, exact upstream commit, resolved dependencies/toolchain, board/partition configuration, preprocessing and model versions.
- Keep private configuration outside tracked source and supply documented templates.
- Retain tested firmware binaries with SHA-256 and build logs privately; publish only sanitised release metadata/artifacts.
- Record verification status separately: source-recovered, compiled, bench-tested, field-tested and installed-device confirmation.
- Preserve journal/clock/day-schedule/WiFi behavior and capture-health regressions in checks.
- Future updater must verify compatible target, archive existing firmware/configuration and log the actual installed release.  It must not call a proposed MLP port deployed until device evidence confirms it.

Related: ../RT_CURRENT_STATUS.md and draft PR #16.  These requirements are documented; a fully automated release/OTA system is not yet implemented.
