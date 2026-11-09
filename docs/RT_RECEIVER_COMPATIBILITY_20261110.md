# RT receiver compatibility handoff, 2026-11-10

## Verified from owner's field evidence
- Running Windows Python receiver process: `python.exe receiver.py` (PID 30728 at inspection). The actual working directory is not yet verified.
- Uploaded October 31 `receiver.py` accepts only `POST /clip`, `POST /journal`, and `POST /rt-log`. No `do_GET`, explaining repeated `GET /rt-control/bcd3d73f1fb8` HTTP 501.
- SD device clips in `WiFi_Backup/Clips/106b508fee68` are **not** RT device clips; RT device ID is `bcd3d73f1fb8`.
- Original receiver wraps SD PCM into 96-kHz WAV. RT PR #24 specifies separate authenticated 192-kHz `POST /rt-clip`, `GET /rt-control/<device>`, `POST /rt-control-ack/<device>`, and `GET /rt-model/<sha>`.
- Owner's RT control file has `wav on` command `42b22bab001b4699aac2f2e80478cfeb` and matching accepted acknowledgement. It will remain acknowledged and must not be assumed to be pending.
- RT firmware log reports `wav=on` but `completed=0` and increasing `skipped_busy`; new receiver alone will not fix capture/inference.
- Individual RT WAVs under RT_Clips not yet verified. Run Bat Daily RT WAV -> BMP -> FastReview still requires separate integration.

## Tested optional replacement, not deployed
A new **separate** `receiver_extended.py` compatibility wrapper and `test_receiver_extended.py` were generated as downloadable conversation artifacts, alongside `RECEIVER_INSTALL.md`. The files are **not installed** on Windows or committed into this repo; no existing receiver/config/audio is changed. The wrapper imports existing `receiver.py` and uses its existing `receiver_config.json` tokens, adding PR #24 protocol routes. SD endpoints remain delegated unchanged. It stores RT PCM16 mono 192-kHz WAVs plus JSON metadata under `WiFi_Backup/RT_Clips/<device>/<date>`. Model binaries are SHA-verified. Control ACK checks pending-command ID before writing. Uses Windows local timezone for generated dates rather than requiring zoneinfo/tzdata.

Local isolated HTTP test suite: 4 tests passed for legacy SD and RT-log routes, RT upload/dedup/conflict, token checks, control poll/ACK and model retrieval. **No field hardware/Windows verification yet.**

## Owner deployment gate
1. Verify actual receiver launch directory and adjacent existing token configuration.
2. Copy companion wrapper beside original receiver.py without overwriting original.
3. Smoke-test temporary port 8766 with current process still on 8765.
4. Stop original process and start wrapper on 8765 with original receiver path, existing credentials, and original root. Confirm old SD uploads and RT control GET no longer returns 501.
5. Inspect RT `/rt-clip` attempts, RT status counters, and real WAV receipts. Preserve ability to roll back by restarting the original receiver. Do not label Daily RT ingest complete based solely on endpoint repair.

Related implementation: PR #24 `firmware/meshcore_wildlife/rt_mlp_update/receiver_extension.py`; Daily roadmap issue #27.
