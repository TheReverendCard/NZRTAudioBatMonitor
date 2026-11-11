# XIAO RT first-pass detector update for COM8

PASS-1 is a candidate firmware for the deployed NZRT-J4-SHARE-1 board.  First installation uses the existing legacy activity trigger for recordings and runs the evolved detector in shadow.  The bench check finishes with those settings, WAV on, downstream MLP in shadow and the automatic day/night schedule enabled.

## Install and verify

1. Extract the entire ZIP to a normal folder in Downloads.  Bring the board in and connect its USB data cable on COM8.  Close Arduino Serial Monitor and other COM8 sessions.
2. Close the old receiver and run Start_PASS1_Receiver.cmd on the usual receiver PC.  Wait for READY or ALREADY RUNNING with PASS-1 verified.  Leave the receiver running.
3. Run Deploy_PASS1_COM8.cmd from the extracted folder.  It patches the known SHARE-1 PlatformIO project, compiles, uploads and opens the serial field check.  A different project location can be passed as a quoted argument.  A source mismatch names the file; retain local changes for comparison.
4. Keep the tester quiet during the detector switching check.  When prompted, play the repeating dual-signal tester for about 20 seconds.  The check looks for advancing windows on all three detectors, then a shared candidate, both journal entries, its parent WAV ACK, the matching continuous 384,000-sample receiver WAV and a synced AUTO schedule.  The RT_pass1_*.log is written beside the launcher.  A timeout leaves the specific field result unverified.  Run py -3 field_check.py from this folder to repeat without uploading.  The bench generates ordinary test-triggered files in RT_Clips during this check.

## Field controls

Use WiFi_PASS1_Controls.cmd, select the RT, then option 11.  Choose status or an active detector (legacy, evolved, audible) and an optional, different shadow detector.  Active determines which activity can trigger a clip.  Shadow records decisions for comparison.  The downstream WAV MLP has separate controls.  Selecting legacy with shadow off removes both experimental filters from the running DSP path.  Choices persist after reboot.  Status includes requested and applied profiles; a sleeping board may wait until monitoring resumes to apply a change.  A queued change may take until the next Wi-Fi poll.  Read the board acknowledgement in WiFi_Backup/RT_Controls/<device>.ack.json.  USB examples are nzrt pass status and nzrt pass legacy evolved.

PASS-1 reports first-pass hot windows and processing times.  Windows are 20 ms and many can belong to a single pass.  Counts accumulate across selection changes; compare differences between status snapshots.  last_us and worst_us cover the additional first-pass computation.  Evaluate the MIC input gaps, dropped blocks and actual continuous WAVs alongside these times.  Use Restore_SHARE1_COM8.cmd to restore the backed-up SHARE-1 source and reflash COM8 if needed.

## Evidence and SD handoff

The full desktop replay reported 7,191 unique clips and zero issues.  Among the 69 confirmed bats and 5,641 noise clips in the supplied comparison, evolved retained 68 bats and suppressed 4,874 noise clips.  Audible retained 69 bats and suppressed 3,121 noise clips.  Those are saved-clip comparisons.  Continuous on-device detection uses a running background, so its field performance still needs measurement.  Neither pulse-count fallback recovered the known miss.

Host C++ checks exercised profile changes and input-gap recovery.  The two experimental detectors matched the desktop decisions on 500 windows from five supplied RT WAVs and 100 windows of synthetic input that gave positive and negative decisions on both detectors.  Installer apply, repeated apply, byte-for-byte source restore, and receiver control request, ACK and readback passed locally.  ESP32 target compilation, board timing, wireless delivery and overnight field performance remain pending on the user's setup.

SD follow-up for issue #45: port the same profile names, active/shadow semantics, settings readback and decision logging.  Benchmark capture continuity and compare retained bat passes before promoting a new default on either recorder.  This package targets the RT only.
