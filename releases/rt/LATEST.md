# Latest RT firmware update candidate

[Download RT_MLP_Update_v0.1.zip](RT_MLP_Update_v0.1.zip)

Build:  `NZRT-MLP-1-JOURNAL-2`  
Status:  Compiled successfully; hardware and overnight validation pending.  This is the latest update candidate on this branch, not a claim about the firmware currently deployed.

## Included

- WAV MLP v0.1 in shadow mode by default alongside the original detector.
- Optional WAV uploads, initially disabled.
- USB and WiFi controls for upload settings and recogniser shadow/active classification.
- Compatible numeric model updates over WiFi, with hash/schema verification and a return to shadow mode.
- Existing WiFi logging and JOURNAL-2 fixes.

## Install

Extract `RT_MLP_Update` into `C:\Users\revje\Documents\Bat`.  Run `Install.bat`, then connect the RT, close Serial Monitor, and run `Update RT.bat`.  Follow the included README to start the extended receiver and configure controls.  Schedule deployment during daytime so the current night's monitoring is not interrupted.

## Provenance and limits

Source commit:  `d963554d97bf4b5a04fa6fe0d6ffb875f5688341`.  
Archive SHA-256:  `6f7f82d1ceda72d698f626e5a2d1278453842af060bc133ce8a5bb462e99c424`.  
Archive:  158470 bytes, 47 files.  ZIP CRC and all payload manifest hashes verified when publishing.

The full target build passed; the included build receipt records its details.  No device has been flashed or hardware verified by this publication.  Automatic Daily Run ingestion of the new RT WAV location remains pending.  This package does not implement firmware OTA or a new LoRa bat-alert packet.

See [PR #24](https://github.com/TheReverendCard/NZRTAudioBatMonitor/pull/24) and [source documentation](../../firmware/meshcore_wildlife/rt_mlp_update/README.md).  Keep local build receipts and receiver credentials private.  The archive contains sources and the numeric model, not a device-configured firmware binary.

This repository copy and `latest.json` preserve the downloadable update independently of temporary chat downloads.
