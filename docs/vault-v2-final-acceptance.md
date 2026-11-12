# Vault v2 final acceptance — 2026-11-12

## Latest remaining acceptance execution

- Full Chromium: **8 passed, 3 skipped**, 85.59 s
  (`artifacts/v2-secure-browser.log`). New chat/ALLOW/MASK included.
- Removed brittle Playwright HTTP response-rewrite transport. A session TCP
  forward binds test-container localhost:8080 to webui:8080. Secure-context reveal
  test requires actual CacheStorage/ServiceWorker APIs; cross-user storage test
  asserts both available. No API-unavailable-as-PASS fallback for these runs.
- Navigation waits for DOMContentLoaded rather than all resource completion.
  Historical 503 **not conclusively diagnosed**: direct error/injection/leak
  scenarios all returned expected checked responses in 0.28–0.44 s. Clean rerun
  is evidence of current operation, not proof of historical root cause.
- Added authenticated `/cleanup-expired`, batch limit 500, SKIP LOCKED. Only
  expired mappings can be deleted: failed WebUI commits retain mappings until
  TTL, preserving reused live tokens. No immediate deletion by guessed ownership.
  Endpoint tested only in isolated image `ai-fire2-vault-v2-acceptance:cleanup`;
  **not deployed to working Vault and not automatically scheduled**.
- Isolated cleanup test: **PASS** live orphan/reuse retained, concurrent cleanup,
  expired deletion, replacement and reveal-role denial. Expiry in this test is
  forced; it does not replace earlier real-wait TTL evidence. Partial commit is
  simulated by withholding message attachment, not an injected WebUI SQL failure.
- Nonbrowser regression: **101 passed**, 12.21 s, one dependency warning.

Overall remains **NOT ACCEPTED**: historical 503 root cause, real WebUI commit
fault, comprehensive PostgreSQL/log scans and explicit output-DLP outage rerun
are still outstanding. Three skipped browser fault tests are not acceptance.

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