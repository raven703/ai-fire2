# Vault v2 final acceptance — 2026-11-12

## Restore diagnosis and new execution (supersedes restore FAIL below)

Original cause: copied OpenBao storage had ownership incompatible with runtime
UID 100, including mode-0700 directories. Server exited before unseal with
`Unable to read storage migration status`. Initial backup also contained a nested
`data` directory from repeated copies. Existing failed copies are preserved.
New executions use unique backup paths and Compose projects/new volumes; restore
sets storage ownership to 100:1000 before starting OpenBao. No working volume used.

`python3 scripts/accept-vault-v2-remaining.py`: **PASS** rotation, revoked
credentials, both dependency outages on STORE/REVEAL, 48 race operations, database
uniqueness/ciphertext invariants, multi-scope fixtures, paired backup, separate
restore and decryption, foreign tenant/user/chat denial and corrupted-ciphertext
denial. Evidence: `artifacts/v2-restore-diagnosed.log`.

Full nonbrowser regression: **101 passed**, one deprecation warning.
Chromium latest full run: **7 passed, 1 failed, 3 skipped**. The failure was a
503 instead of expected 200 during model-failure scenario. Targeted rerun:
**1 passed, 1 failed, 1 skipped**, failure was navigation timeout. Do not claim
clean browser regression. Native health afterwards: 200.

Cross-user test and reveal persistence test passed in the latest full run.
Reveal test now scans IndexedDB values, available CacheStorage/ServiceWorker
APIs, logical WebUI DB and raw DB/WAL/SHM for its fictional-name fixture.
Cache/worker APIs are absent on Docker HTTP origin: full secure-origin sweep is
**NOT TESTED**, not silently accepted. Comprehensive PostgreSQL/log sweep and
safe orphan cleanup remain **NOT TESTED / NOT IMPLEMENTED**. Stage A overall
remains **NOT ACCEPTED**. No Native runtime security controls changed.

**NOT ACCEPTED. Synthetic-only.** Working volumes were not used for faults.

Command: `python3 scripts/accept-vault-v2-remaining.py`.
Evidence: ignored `artifacts/v2-remaining-acceptance.log`.
Projects: `ai-fire2-v2-acceptance`, `ai-fire2-v2-restore`.

| Requirement | Result |
|---|---|
| Real-wait TTL / restart readiness | PASS previously; not repeated |
| Transit encryption key rotation, old ciphertext readable | PASS |
| Encryption/decryption credentials replaced, old rejected | PASS |
| OpenBao outage on STORE/REVEAL | PASS: 503, no fixture in response |
| PostgreSQL outage on STORE/REVEAL | PASS: 503, no fixture in response |
| 48 concurrent STORE/REVEAL/DELETE | PASS for status contract (200/404); not proof of linearizability |
| Quiesced paired PostgreSQL/OpenBao backup | PASS creation only |
| Restore into separate project and decrypt old mappings | FAIL: runner stopped before verification |
| Orphan cleanup | NOT IMPLEMENTED |
| Native verified-user isolation | NOT TESTED this increment |
| Full persistent-storage/Mock/DB/log sweep | NOT TESTED |
| Full regression this increment | NOT TESTED |

Restore copies retained for diagnosis; no volumes removed. Backup/recovery
material is sensitive and stays under ignored artifacts. Never commit it.
Service rotation covers Transit credentials, not all API or PostgreSQL credentials.
No full stage-A acceptance commit is claimed. A checkpoint is not acceptance.