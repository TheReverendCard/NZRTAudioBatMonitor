# GUARD-4 candidate, 2026-11-15 NZDT

Parent:  GUARD-3 candidate branch at `03b3ab37658aa952f5bf059f110098c2c927f53b`.  Recovered installed identity was NZRT-J5-GUARD-3.  New identity NZRT-J6-GUARD-4, JOURNAL-6, PASS-2 retained.

Owner authorised fixes after the completed GUARD-3 loaded test failed during load11, about 19m37s into the run.  First phase had 366 DSP drops/284 gaps, journal readback faults with an impossible offset and a 1.991-second peak operation.  Later feature scoring occupied clips for about 28 seconds.  A watchdog abort followed timed journal recovery.  These are engineering tests, not evidence of bat classifier precision/recall.

Implemented:  safe new-file append start, file-length validation, bounded RAM journal and hash-acknowledged uploads, physical capture-stop gate for flash persistence, boot-latched journal failures, no automatic quarantine/retry, cached storage diagnostics, fair report/ML network turns, exact integer FIR, internal-RAM hot feature scratch, 4 ms cooperative yielding, runner timings and post-reset diagnostics, and an integrated GUARD-3-to-GUARD-4 backup/build/upload workflow.

Preserved:  original source project, pin assignments, sample rates, detector thresholds/PASS-2/RT-SCORE-1, model schema and weights, downstream shadow/active selection, WAV switch, receiver credentials/endpoints, score/WAV leases, pressure fallback, one-hour test expiry and rollback receipts.

Validation and installation state are in `evidence/` and `README.md`.  No physical board was flashed here.  Await the owner build/upload receipt and all four loaded phases before field qualification.  Do not mark recogniser sensitivity or S3 speed-up measured from host/emulator checks.
