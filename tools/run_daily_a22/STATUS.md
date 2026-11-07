# Run Daily A2.2: owner-installed source compatibility merge

**Recorded:** 8 November 2026. **Status:** host/synthetic-tested ZIP delivered in ChatGPT, not installed/field-verified on owner's Windows PC, not merged/released. This branch documents exact sources, compatibility gates, test evidence and remaining tasks; it does **not** contain the complete 31 KB ZIP payload. Keep #27 and #26 open.

## Reason for the merge
The A2.1 preview correctly rejected the owner-installed `review_unreviewed_queue.py` and `daily_pipeline.py`, because newer RT audio review/processing changes had been made since A1. The owner uploaded **both actual installed sources** for non-destructive reconciliation. The resulting A2.2 package applies the A2.1 BMP-integrity and external-import hooks **to those exact installed versions**, retaining their existing RT code.

### Exact source gates (SHA256 of LF-normalized UTF-8 source)
| File | Owner-installed input | A2.2 output after patch |
|---|---|---|
| `BatDailyTool/review_unreviewed_queue.py` | `6fc5cb32bd4617ef7fcc2f70ba14496f0ef3150644033707c5fa9b295d66fdef` | `b7f34b4e45377270fff99dde76360f089479c7ae495207135b9cc4fbf3ba6557` |
| `BatDailyTool/daily_pipeline.py` | `1c0eb339efffe1580828bd25dde1142aebf68b8505508ea4bd4a26d60b1307e9` | `ffd3f815e46135f528819c36f42fa96c8e979b2257993af122f3feaf09b992d1` |

Installer refuses any other local version, retains original line endings, verifies its after hash, backs up changed source bytes under `Tool_Backups/RunDaily_A22_*/before.zip`, restores only when installed source hashes remain unchanged, and recognises fully installed A2.2 scripts on subsequent previews. No blind overwrite of unrelated newer source code.

### Source ZIP artifact delivered
- Conversation artifact: `BatDaily_A2_2_Compatible_RTDaily_External_Review_TEST.zip`
- SHA256: **`3b0245a527670d5b3bb163a07325d16334c168aa30ed89e90c3e04a07e24cea2`**
- Total: **31,358 bytes**, **15** files, ZIP CRC verified.
- Root inside ZIP: `RunDaily_A2_2/`; entrypoints: `Preview A2.2.bat`, `Install A2.2.bat`, `Restore A2.2.bat`, independent read-only `Check Review BMP Integrity.bat`, and previously tested `Fix GUI Only.bat` (owner reports GUI guard already installed).
- Source components: `install_a2.py` guarded source-anchor patcher, `external_import.py` managed AR4 intake, `bmp_health.py` source-integrity gate, `fix_gui.py` optional GUI guard, version/sha manifest, standalone tests, README.
- **Do not call this GitHub branch a full source mirror**. For full code recovery use the above verified ZIP from the owner's ChatGPT conversation, or request a source commit to the repo in a later step. Do not guess a sandbox URL elsewhere.

## Implemented in candidate code, not yet field verified

**Queue protection:** check original BMP file header before counting as actionable. A zero/truncated/non-BM BMP is written to `Daily_Run_Reports/FastReviewQueue/unreadable_media.json`, not deleted/graded/treated as negative. An old untouched staging hardlink may be retired without changing the original; a modified working annotation remains as conflict. If every file is unreadable, don't open a blank GUI. On normal queue exit with no grades, log explicit warning.

**External AR4:** read-only SHA/stability inventory under `External Data/Mara Kokotoha/Shed/YYYYMMDD`, `.../South/YYYYMMDD` and `External Data/Other/YYYYMMDD`. Working BMP copies ONLY under `Daily_Run_Reports/External_Import/Managed/<site>/<date>/`. Preserve existing source sidecars and owner human review; never overwrite with reconstructed machine output. Existing hash-pinned stock AviaNZ CLI classifies only managed BMPs with no authoritative sidecars; original machine `Backup` manifest retained. The same Fast Review queue receives managed ungraded BMPs; explicit human hotkey grades are joined to `External_Import/reviewed_candidates.csv` for future **separate** training audit. Treat copy/hash/site conflicts as partial, not data loss. Exclude South/Other from Shed index JSON and all daily activity. Source-matched Shed canonical copies dedup, other new external Shed media remain training/review only pending canonical index integration.

**Preserve current owner-specific additions:** `daily_pipeline.py` continues to execute `rt_audio_daily.classify_received(root,auto)` after CLI setup; queue continues to enumerate `XiaoRTYYYYMMDD` and require `.rt.json` provenance. Original machine model SHA and stock NZ Bats filter remain unchanged. No model weights, reviewed media, source files, GUI/FastReview 1–5 functionality or field firmware edited by source installer itself.

### Verification evidence
- **16** Python unit/integration tests passed locally, including source immutability, exact managed sidecar preservation, canonical Shed alias, cross-site collision rejection, GUI anchor, backup/install/rollback under exact source SHA, idempotent post-install preview, source-level RT hook preservation.
- Additional end-to-end **simulated 85 BMPs**: 83 structurally valid, 2 zero-byte originals. Source scan returns 83 actionable and 2 unreadable. Preparing and resuming queue retires stale untouched invalid staging hardlink, keeps 83 reviewable hardlinks, leaves zero-byte source originals unchanged. No field AviaNZ GUI decoder verification.
- Original owner Windows diagnostic: **85** staged, **83** plausible, **2** zero-byte (both source & staged), **0** NTFS hardlink problems; source filenames `20260419_044653.bmp` and `20260419_212318.bmp`. The owner has **not** verified 83 grade saves after this A2.2 install.

## Known remaining gates and limitations
1. Windows A2.2 preview/install must show no blockers against actual files, then Fast Review must open first valid BMP, allow grade saving and queue counts (the initial A2.1 preview did not install). Verify `83 actionable / 2 unreadable` only if no new imported media/reviews changed backlog.
2. The new managed External Data importer must be field tested with actual SD-card date folders, stock AviaNZ CLI results and source-sidecar preservation; imported external counts appear in administrative review queue, NOT Shed index.
3. Reviewed external examples **are not yet** in frozen LR/MLP/CNN training manifests; `reviewed_candidates.csv` is a candidate list only. Future external reference WAV/FLAC and new noncanonical Shed index entries remain pending.
4. XiaoRT host/firmware work from #24 and owner-installed `rt_audio_daily` are preserved, not reimplemented/tested on hardware here. No active ML model promotion.
5. Avoid concurrency of Run Daily, Fast Review, or another AviaNZ window on managed staging; existing shared lock and backups remain.

Related: #13 review/backup pipeline, #26 external corpus and Shed scope, #27 12-item roadmap, PR #28 A1 history, #24 RT upload.
