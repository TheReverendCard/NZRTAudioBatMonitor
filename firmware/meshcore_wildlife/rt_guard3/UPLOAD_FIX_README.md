# GUARD-3 combined upload fix, revision 3

**Run this patch only.  It includes both the serial correction and the merge-bin.py correction.**  It accepts the original GUARD3 tools or tools already updated with the serial-only patch.

1. Extract `NZRT_GUARD3_Upload_Fix_v3.zip` to a new folder.
2. Run **Apply Upload Fix.cmd**.  Choose your existing GUARD3 tools folder containing **Backup and Upload.cmd** and **last_candidate.txt**.  Default is `C:\Users\revje\Documents\Bat\Firmware\GUARD3_Tools`; nested `NZRT_GUARD3_Prep` folders are recognised.
3. Close Serial Monitors.  Run **Backup and Upload.cmd** from that existing tools folder, then choose **COM8**.
4. After a successful upload, continue with the new receiver and **Run Loaded Test.cmd** as previously instructed.

No firmware rebuild or Install.cmd rerun is needed.  Existing build selection, virtual environment, credentials and compiled firmware are preserved.  The installer backs up the previous tool scripts under `Tool_Backups/upload_fix_<UTC>` and adds the merge repair helper.  It does not connect to the board.  Unknown tool versions stop before modification.

The corrected uploader uses CRLF and retries the read-only identity query.  It also backs up the known candidate `merge-bin.py` and changes only `Import("env", "projenv")` to `Import("env")`.  The script never uses projenv, which is absent during a nobuild upload.  Its binary-merge target is preserved.  Unknown merge-script versions stop untouched.  The compiled firmware is not rebuilt or replaced by this repair.

The upload step still requires the expected GUARD-2 identity, source/image hash checks and a complete 8 MB flash backup.  If upload fails again, it prints the last 40 lines of upload.log and the full log path.  Share that text.  For identity failure, share identity.json and before_serial.txt from the printed report folder.  Keep full-flash backups private.

Repair rollback:  close the tools, restore backed-up PC scripts from Tool_Backups, and remove merge_upload_fix.py if its receipt shows before_sha256 null.  Restore the candidate merge-bin.py from `PreUpdate_Backup/merge_bin_<UTC>` if reverting that script is required.  This reverts PC tooling only.  Device rollback uses the separate full-flash backup printed by the uploader.

Validation:  19 host tests passed, including reproducing the exact import failure with real SCons and dry upload-target dispatch after repair.  Original and serial-patched installations verified.  Full Windows PlatformIO/USB upload still requires your retry.  This patch changes no recogniser or firmware behaviour.
