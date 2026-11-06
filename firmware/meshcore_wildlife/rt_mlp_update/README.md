# Xiao RT MLP update candidate

Build ID: `NZRT-MLP-1-JOURNAL-2`.  Prepared 6 November 2026 from the recovered `NZRT-FIELD-PILOT-5-WIFI-2-JOURNAL` sources.  Xiao SD firmware is not changed.

## Install

1. Extract `RT_MLP_Update` into `C:\Users\revje\Documents\Bat`, beside `bat_config.json`.  Run `Install.bat`.
2. Leave the RT connected and close Serial Monitor.  Run `Update RT.bat`.  The saved project and port are offered automatically.  The correct recovered project is `C:\Users\revje\NZRTAudioBatMonitor-meshcore\NZRT-MeshCore-NZBat-BandMonitor`.
3. The updater checks source hashes, backs up the complete RT journal, backs up changed source and existing build images, compiles, uploads, then checks firmware identity, model-worker allocation and JOURNAL-2 append/readback.  Build failure restores previous source without flashing.  Upload or startup-check failure is reported and keeps the backups.
4. For WiFi controls, model downloads or RT WAV uploads: stop your existing receiver, then run `Start Extended Receiver.bat`.  Select its existing `receiver.py` once.  The extension imports that receiver and uses its existing `receiver_config.json`, including additional SD tokens.  Do not start two receivers on port 8765.  The selected receiver and output folder are saved in `bat_config.json`.
5. First installation starts in **shadow mode with WAV uploads OFF**.  Check `NZRT ML_STATUS enabled=1` and a healthy journal.  A startup PASS is not a successful overnight/acoustic test.

`Build Only.bat` performs the same source validation and compilation but does not connect to or flash the device.  Later installations preserve saved controls.  Reports, journal backups and firmware binaries remain private under `Bat\Update_Reports\RT_MLP_<UTC>`.

## Controls

Use **WiFi RT Controls.bat** to queue one command for a known RT device.  The RT polls about every 30 minutes, with the first poll about two minutes after startup/time synchronisation.  This adds brief WiFi connection attempts even when WAV upload is off.  If offline, it retries after 60 seconds.  A queued command survives device restart and is deduplicated by its request ID.  The receiver saves a `.ack.json` when the command has been accepted; acceptance of a model-fetch request is not proof that the model has finished installing.

Use **RT Controls.bat** for immediate USB controls.  The corresponding serial commands are:

| Command | Effect |
|---|---|
| `nzrt ml test` | Daytime synthetic-silence feature/model test, reporting timing without creating a detection |
| `nzrt ml status` | Model identity, mode, WAV setting, completions, dropped opportunities, gaps, upload counters |
| `nzrt wav on` | Save subsequent captured review clips to the WiFi receiver |
| `nzrt wav off` | Stop future uploads and release queued audio buffers; keep summaries |
| `nzrt ml shadow` | Original detector remains the selected detector; log MLP predictions separately |
| `nzrt ml active` | Select MLP classification for subsequent captured candidates; retain original candidate records |
| `nzrt model fetch <SHA256>` | Download a staged numeric model over WiFi when daytime standby and buffers are idle |
| `nzrt model builtin` | Restore the compiled model in shadow mode during daytime idle |

WiFi promotion requires the exact model identity, so a queued promotion cannot accidentally promote a different newly installed model.  Built-in identity is `builtin-wav-mlp-v01`.  Updated models use their full package SHA-256.  Rejected commands remain pending for inspection.  The GUI refuses to overwrite an unacknowledged command; inspect/remove `WiFi_Backup\RT_Controls\<device>.json` if you deliberately want to cancel it.

**Meaning of promotion:** this is a second-stage classifier for candidates raised by the existing 18–45 kHz energy trigger.  An active-mode `NZRT ML` record supplies the selected bat/not-bat candidate classification.  It does not replace that first-stage trigger or create a new species ID.  Original `NZRT CANDIDATE` records remain available and are the fallback for unavailable, invalid or skipped ML processing.  Existing Daily Run summaries still use their existing candidate parser unless explicitly extended to join these new ML records.  No new LoRa bat-alert packet is introduced in this update; MeshCore operation remains intact.

## Audio capture and workload

- One two-second **192 kHz mono PCM16** review clip begins 250 ms before the triggering window ends and continues for 1.75 seconds.  This is a new RT review capture, not a copy of a Xiao SD recording.  The trigger-window onset is about 20 ms before its end.
- Two fixed clip buffers, one 250 ms pretrigger ring and one reusable feature workspace consume about 2.3 MB of PSRAM.  The original microphone reader remains high priority.  A separate lower-priority worker performs features and inference.  No file/network operations run in the reader or DSP callback.
- Bounded buffers can fill while scoring or uploading.  Further ML capture opportunities are counted as skipped, while the original detector continues.  A PDM gap or stop invalidates a partially filled clip; invalid results are not negative labels.
- WAV upload is optional and uses `/rt-clip`, never the SD `/clip` endpoint.  RT files go into `WiFi_Backup\RT_Clips\<device>\YYYYMMDD\YYYYMMDD_HHMMSS_RT_<session>_<run>_<seq>.wav`.  Names use Pacific/Auckland local time; JSON receipts preserve UTC and identify Xiao RT.  Session/run/sequence prevent collisions and join to ML journal records.
- No RT WAV is written to internal flash.  There are at most three send attempts, with 60-second retry spacing and a five-minute queue expiry.  Power removal loses pending RAM audio.  Summary journal retention remains JOURNAL-2.  Upload-off takes effect after any already in-flight HTTP request completes.
- HTTP work is still performed by the main network service and can delay MeshCore main-loop servicing for connection/transfer time.  Audio tasks remain independent, but shared CPU, memory and WiFi activity can cause additional gaps.  This is not yet a measured zero-loss or low-power implementation.
- The model was trained on recordings with varying durations.  A two-second RT trigger-centred window is a changed sampling policy and needs field comparison even when numeric feature parity passes.  The initial threshold remains the supplied validation threshold; it is not automatically retuned.

## Models and updates

The built-in model is the user's WAV MLP v0.1, StandardScaler then 165→32→16→1 with ReLU/ReLU/logistic.  Source joblib SHA-256 is `497ff930552797bb0d2d43ab701f8ffdfe4960dd8d336e2d73ec039c7913d7c4`.  Threshold is approximately 0.98325952.  This implementation uses ordinary floating-point C++ and bounded FFT/features; it is not an ESP-NN INT8/SIMD optimisation.

1. Export a compatible numeric model from the PC training pipeline.  The format is documented in `MODEL_FORMAT.md`; the optional `export_numeric_model.py` consumes numeric NPZ with `allow_pickle=False`.
2. Run `Stage Model.bat` on its `.bin`.  It validates schema/shape/finite parameters, then places the package in `Bat\Models\RT\<SHA256>.bin`.
3. Queue “Fetch a staged model” in `WiFi RT Controls.bat`, or use the serial fetch command.  The extended receiver must be running at the existing configured URL/token.  Download is deferred until daytime idle.
4. The firmware checks size, architecture/feature schema, parameter validity, SHA-256 and flash readback.  It writes the inactive model slot before committing the new selection to NVS.  A failed update retains the current model.  A corrupt saved model at boot falls back to the built-in model in shadow mode.
5. Every installed model begins in shadow mode.  Promote it explicitly after comparing its results.  Compatible weight/threshold updates do not need a firmware reflash.  A different feature schema or network shape requires a new firmware build.

Model files and commands use the existing private-LAN bearer token.  The hash verifies the exact requested package, but this is not Internet-facing TLS or signed release distribution.  There is no automatic download/promotion of the latest GitHub model.  Firmware OTA and new LoRa command transport are not implemented here.

## Review the first run

Run `Summarise RT ML Logs.bat` after WiFi journal uploads arrive.  It creates `Bat\RT_ML_Review\RT_ML_All.csv` and `summary.json`, deduplicating overlapping snapshots by session/run/seq/model/mode.  It never changes recordings, annotations or training labels.  Existing Daily Run is unchanged.

While the RT is still connected in daytime, use RT Controls option 8 to run the synthetic model self-test.  It should report `NZRT ML_TEST result=PASS` and its processing time.  This checks the real MCU pipeline but not microphone fidelity.

Useful evidence: the updater `after.txt`, a complete overnight RT TXT snapshot, `RT_ML_All.csv`, and several uploaded RT clips with their JSON receipts.  Compare ML completions and `inference_us` with `skipped_busy`, `dsp_drop`, `input_gaps`, and original candidate counts.  Keep shadow mode for the first overnight comparison.  A model probability is an uncalibrated classifier output, not a human confidence grade.

## Recovery

Keep the recovered JOURNAL-2 project/build receipt and this update's source backup.  `Restore Previous Sources.bat` restores only the files changed by the selected update; it refuses if subsequent edits are present.  It does not flash automatically.  Rebuild/upload the restored target using PlatformIO or the prior updater when intentionally rolling the device back.  Never run a filesystem erase to change models or firmware.  Preserved binaries and logs can contain private receiver configuration; do not publish them.

See `VALIDATION.md` for actual test results and remaining hardware checks.
