# Vault v2 verification — November 12, 2026

Status: **partial implementation, not migration/security acceptance**. Native
runtime remains unchanged on its synthetic-only Vault; no real PII enabled.

## Latest containment and UI verification

Root disclosure source: subprocess.CalledProcessError included argv containing
`BAO_TOKEN` during failed provisioning. One-time containment now passes secrets
only through stdin and suppresses command stderr/exception bodies. Revealed root
token revoked; subsequent lookup returns 403. Previous common service credential
revoked. Separate encryption/HMAC, decryption and rotation-only credentials issued.
Runtime receives only exact secret files, not init/unseal/operator material.
Encryption roundtrip/isolation/tamper tests passed after revocation. Local artifact
scan found zero matches for the revoked root value; external tool transcript cannot
be erased, but its credential is invalid. Full Git/log secret inventory is not yet
accepted. One-share unseal remains a local test limitation.

Original UI rebuilt under memory watchdog: exit 0, no watchdog stop. Deployed
new source image. Fixed native socket initialization and auth's null socket access.
Config transformation disables compression for its internal upstream call, avoiding
gzip JSON decode failure discovered by Chromium. Exact-permit transactional delete
and owner-only masked read/preview deployed.

Chromium test: authenticated original composer, `Иванов Иван` masked, no socket
requests, no reconnect warning, preview GET contains no original, delete succeeds
and subsequent GET is 404: **PASS**. Preview/delete checked using page API requests,
not sidebar hover/menu clicking. Final browser suite **7 passed, 3 skipped** (fault
scenarios not rerun in this increment). Full nonbrowser regression **100 passed**.
POC and Native restarted; data/volumes retained.

| Requirement | Status |
|---|---|
| Revealed root revoked, rejection verified | PASS |
| Old common service token revoked | PASS |
| Split Transit credentials operational | PASS |
| Encryption/reuse/scope/tamper/deletion | PASS |
| UI rebuild and basic native operations | PASS |
| Full nonbrowser regression | PASS |
| Full credential inventory incl. Git/logs | NOT TESTED |
| TTL real expiry / dependency outages | NOT TESTED |
| Restart with unseal / backup restore | NOT TESTED |
| Key/service credential rotation lifecycle | NOT TESTED |
| Concurrent requests/delete races | NOT TESTED |
| Reversible Native MASK/display-only reveal | NOT IMPLEMENTED |
| Browser storage/LLM replay after reveal | NOT TESTED |

Earlier partial statements below are historical; this update supersedes root/UI
status only. Vault v2 remains isolated, not the active Native Vault.

Implemented separate PostgreSQL 17.7/OpenBao 2.5.0 contour. OpenBao Transit
AES-256-GCM encrypts originals, with contextual associated data binding scope,
random 256-bit token and expiry. Separate HMAC key supports scoped stable reuse.
Keys stay in OpenBao; PostgreSQL contains ciphertext/keyed lookup only.
Read/write API credentials separated. Tokens expire and deletion is available.
Store API accepts only `SYNTHETIC_V2_...` fixtures and final MASK policy version.

Actual container tests passed: encryption roundtrip, stable reuse, user/chat/
tenant isolation, differing tokens across scope, BLOCK/REVIEW rejection, reveal
role separation, ciphertext tamper rejection, deletion and absence of tested
original value from PostgreSQL mapping rows. Evidence:
`/home/user/ai-fire2/artifacts/vault-v2-tests.log`.

OpenBao volume initially had incorrect ownership; fixed for UID 100/GID 1000.
Test init uses one unseal share held in ignored local artifacts. Root material
and service token remain local and must not be published. A failed provisioning
command exposed the test root token in tool diagnostics; root credential must
be rotated/revoked before any stronger acceptance. Service uses restricted token.
Transit lookup key uses AES key type supporting HMAC, not unsupported `hmac` type.

Limitations: TLS disabled on internal local test network, DB role is currently
bootstrap owner, no automated token renewal, audit pipeline, rewrap tooling,
backup/restore or recovery acceptance. TTL expiry/restart/outage tests outstanding.
Gateway migration adapter built and started. Actual HTTP smoke test passed:
MASK returns a token without original; full-batch BLOCK/REVIEW denied. This
adapter remains separate from the accepted Native Gateway. No Native reveal UI
or proof that display-only demasking avoids browser persistence and LLM replay.
No claim of completed Vault v2 or production readiness.

UI source fixes added for masked read-only preview, exact-permit transactional
deletion and suppressing socket setup only for server-advertised native text
mode. These source fixes have not yet been rebuilt/deployed/browser verified.
Do not treat current deployed UI as fixed until that verification is executed.