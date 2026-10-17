# Pixel 6 Pro development and field plan

Status:  planned implementation, 17 October 2026.  No Android app has been implemented in this repository.

## 1. Document and test the physical setup

Record the Android version/build, EMT2 variant, USB hub/switch model, charger, extension type/length and available storage.  Document the actual power and data connections.

Keep the existing automation that enables charging at 20% battery and disables it at 80%.  The recorder should log battery and charging state.  Verify that changing charger state does not interrupt microphone power, USB data or the phone's host role.  Log interruptions and recovery if it does.

Test with the actual deployment extension.  Compare against a short connection if needed.  Position the EMT2 close to the AR4, with documented spacing, orientation and weather protection that leaves the microphone opening unobstructed.

## 2. Build a minimal Android capture diagnostic

Enumerate the input, obtain the required access, record a short unprocessed WAV and export a diagnostic report.  Investigate the Android capture route on the actual OS/device before choosing a USB library.

Target 256,000 samples/s, mono, signed 16-bit PCM, the format previously demonstrated on Windows.  Native capture in our Android app remains unverified.  Report unsupported formats explicitly and never silently fall back to the phone microphone or ordinary-rate audio.

Record input identity, requested/reported format, sample count, elapsed time, interruptions and errors.  Verify actual ultrasonic content, rather than trusting the WAV header.  Measure any startup settling interval and discard or mark it.

Acceptance:  a P6P recording with verified ultrasonic content and accounted-for sample continuity, using the full extension with charging both on and off.

## 3. Build the unattended recorder

Planned requirements:

- User-visible foreground recording service and clear recording state.
- Nightly schedule with explicit timezone and session identifier.
- Rolling buffer and sensitive candidate-activity trigger.
- Configurable pre/post-event audio.  Start by evaluating one second before the trigger and two seconds after activity ends, as used in the desktop experiment.
- Bounded files, with continuation identifiers for sustained events.
- Capture independent of inference, file export and UI work.
- Original WAV clips, JSON metadata and a CSV event index.
- Scheduled background/audit recordings independent of triggering.
- Health logs, storage reserve and explicit storage-full behaviour.
- Recovery after USB loss with documented downtime and bounded retries.
- Complete session export including settings and health records.

At the target format, uncompressed audio uses 512,000 bytes/s, approximately 1.84 GB/hour or 22.1 GB per 12 hours.  Use bounded continuous audits and an explicit retention budget.  Do not silently delete unexported evidence.

Acceptance:  screen-off and overnight operation, valid evidence files and accounted-for gaps.  Test actual charge transitions, USB unplug/replug, low storage, process termination and reboot.  Document any recovery that requires user action.

## 4. Collect paired P6P and AR4 sessions

Record clock offset before and after each session.  Store UTC times, local timezone/offset, and phone monotonic timing/sample positions.  Account for clock adjustments and drift.

Daily, where practical:

1. Export phone and AR4 data.
2. Process AR4 data using the identified AviaNZ version and recogniser.
3. Preserve original annotations and processing settings.
4. Apply documented clock correction and record timing uncertainty.
5. Match events with a defined tolerance and pass-grouping rule.
6. Report matches, missed reference passes, unmatched phone events and downtime.
7. Review examples before changing thresholds; preserve previous configurations/results.

Phone-only detections are unmatched, not automatically false positives.  The microphones and detection areas may differ.  Missing files during unknown recorder availability must not be treated as bat absence.

## 5. Develop recognition using existing and paired data

Inventory available WAVs, BMPs and annotations.  Identify the exact AviaNZ recogniser, preprocessing, weights, decision rules and reuse terms.  Phone classification is a goal; it need not block initial paired recording.

Preserve positive candidates, background, uncertain examples and independent audit recordings.  Add versioned labels without overwriting original capture records.  Separate development and evaluation nights/sites before tuning.

Provisional later deployment gate:

- At least 90% capture of AR4/AviaNZ reference passes during overlapping uptime.
- Report sample size, per-night results and uncertainty.
- Measure false-alert burden through review and assess event-count agreement.
- Agree acceptable uptime and false-alert limits before accepting routine operation.
- Evaluate on held-out field sessions.

This measures agreement with a practical reference, not independently established biological accuracy.

## 6. Agree shared phone/ESP32 data contracts

These are requirements for a future versioned schema, not an implemented format.

| Record | Required information |
| --- | --- |
| Session | Device/session ID, UTC bounds, timezone, software/configuration version, hardware/input identity |
| Event | Stable ID, WAV path/hash, times, sample offsets, sample format, trigger settings, continuation ID |
| Classification | Event ID, label, available scores, recogniser/model and preprocessing versions, label source, review status |
| Health | Capture intervals, sample loss/uncertainty, USB errors, restarts, battery/charging state, free storage |
| Comparison | Reference file/annotation IDs, clock correction, uncertainty, matching rule and match status |

Do not describe uncalibrated scores as probabilities or convert missing data to absence.

Keep features and model conventions portable.  Benchmark capture, preprocessing, inference and SD writing together on ESP32-S3, including peak memory and sustained load.  Initially retain recordings on SD.  Live aggregation follows validation and should retain selected evidence for continued checks.

## Next concrete deliverable

A minimal Android capture diagnostic producing a verified WAV and diagnostic report on the P6P with the deployment USB arrangement.
