# RT intake performance and lossless daily logs

The patch in this folder targets the installed review-first runner inspected on 23 November 2026.  The base source hashes are SHA-256.

| Installed file | Base digest |
| --- | --- |
| rt_logs.py | 84d30a6eb774b26324454962bf8fe2be12a2df7777a538f4f4dbc4d43761da0b |
| review_first_daily.py | e6cb8fef5bd82cf8dba189b3cec5d3d9fb262dcf58cac0d87f1fd17ca473019e |

The inspected installation has later changes than the original review-first branch.  Apply the supplied installer to the matching installation, or use `git apply --check --ignore-space-change installed-runner.patch` from the parent of a matching BatDailyTool source tree before applying this patch.  The patch contains the two program edits, two new modules, focused regression tests and the isolated replay benchmark.  The operator's download also includes the ready-to-use Windows installer and private daily data exports.

## Intake change

The existing runner submitted each changed RT text file separately to the date importer, replaced its date receipt, then searched historical archive sidecars for a digest match.  One morning run spent 1,375.55 seconds importing RT logs before launching human review at 1,421.27 seconds.  The raw archive contained 12,031 receipts after the import.

The new code groups pending receiver text uploads by NZ date, walks the raw receipt directory once and caches digest lookup metadata in the existing task database.  A valid hit requires re-reading the matching receipt, satisfying transfer completeness and method rules, and hashing the archived text.  Newly published receipts enter the lookup immediately.  Unrelated text and unreadable inputs retain separate outcomes.  A date's receipt and dependent work precede the commit that clears its queue.  Progress logs include cold versus cached receipt counts, time spent indexing and the separate new, reused and skipped totals.  The latest intake counters are available through the existing --status entry point.

## Per-device daily logs

After review, each affected NZ receiver date is written under Daily_Run_Reports/RT_Daily_Logs/<device>/YYYYMMDD.zip.  The date follows the upload timestamp.  The pack includes a first-occurrence text view (daily.log), a per-upload ordered line index (uploads.jsonl), and summary.json.  Exact line repeats, original line endings, unterminated final lines, filenames and SHA-256 values survive reconstruction.  New packs are hash-checked against all original uploads before atomic replacement.  Late uploads can extend a pack even if some of its former sources have since left the receiver.  Existing raw archives continue to supply timeline, audit and recovery workflows.

At the field site, 12,061 receiver files across 24 NZ calendar dates occupied 127,994,451 bytes.  The 24 verified date packs occupied 2,935,027 bytes.  Ten uploads were byte-identical to earlier uploads.  Among 497,942 NZRT lines, 88,483 distinct device/date/line combinations remained in a per-day view.  A current 755-file intake contained 3,832 NZRT line occurrences and 2,635 distinct lines.  The file count alone is a poor indicator of scientific or diagnostic duplication.

## Further performance work

A recent completed run extracted features for 1,834 WAV sources and 6,018 shared-band BMP sources.  Those research training stages took 663 and 542 seconds respectively.  A proposed next optimisation is persistent per-source feature caching keyed by content, extractor revision and settings, with labels, splits, fitting and nightly metrics updated normally.  The timeline parser's cross-file session and clock anchors must be preserved in any per-session parsing optimisation.

## Verification

The targeted RT batch, daily pack and existing RT log tests passed (24 tests).  Four legacy scored-log tests have the same failures before and after the changes.  They cover score fields, partial scored records and the timeline score display.  The Windows installer was checked against a copy of the installed sources, including an idempotent second run.  The update is staged for owner installation.  It has not been run against the live daily workflow.

An isolated replay copied the 11,276 earlier archive receipts and their raw files, then submitted the 755 newly archived receiver uploads from that morning through the updated normal intake function.  Cold intake took 80.92 seconds, including 76.46 seconds to build the lookup.  Re-submitting all 755 with the cache populated took 8.68 seconds, including 0.16 seconds to reconcile 12,031 cached receipts.  The replay verified the archived bytes and date receipts after both passes.  These are host measurements on a copy, excluding fixture setup and post-review pack creation.
