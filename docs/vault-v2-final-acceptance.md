# Vault v2 final acceptance — 2026-11-12

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