# GUARD-3 USB identity fix

**Superseded by the combined NZRT_GUARD3_Upload_Fix_v3.zip.**  Use that package and Apply Upload Fix.cmd once to fix both serial identity and the merge-bin.py nobuild import failure.  The instructions below describe the earlier serial-only repair.

This fixes the updater's command line ending.  The older RT parser requires CR, while the original updater sent LF only.  No firmware was uploaded when the identity check stopped.

1. Extract `NZRT_GUARD3_Serial_Fix.zip` to a new folder.
2. Run **Apply Serial Fix.cmd**.  Choose your existing GUARD3 tools folder, the one containing **Backup and Upload.cmd** and **last_candidate.txt**.  The default searches `C:\Users\revje\Documents\Bat\Firmware\GUARD3_Tools` and its nested `NZRT_GUARD3_Prep` folder.
3. Close Serial Monitors.  Run **Backup and Upload.cmd** from that existing tools folder and choose **COM8**.
4. After a successful upload, continue with **Start Receiver.cmd** and **Run Loaded Test.cmd** from the existing package as instructed previously.

No firmware rebuild or dependency reinstall is needed.  The repair backs up and replaces only `upload_candidate.py` and `serial_link.py`; it keeps your built candidate, `last_candidate.txt`, virtual environment and credentials.  Unknown script versions stop before modification.  Applying the repair does not connect to or flash a device.

The uploader still requires a live GUARD-2 identity and a complete 8 MB backup before uploading.  It now retries using CRLF and prints its connection-report folder.  If it stops again, send **identity.json** and **before_serial.txt** from that printed folder.  Do not send the full flash backup, which contains private configuration.

For installer rollback, the prior scripts and receipt are under the existing tools folder's `Tool_Backups\serial_fix_<UTC>`.  Close the tools and copy those two backed-up scripts back to the tools folder.  This rolls back the PC scripts only, not the device firmware.

Host regression tests passed.  Actual Windows USB upload still needs your run.  Firmware source, model and candidate build identity are unchanged by this fix.
