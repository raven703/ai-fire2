# Text DLP / Vault integration — 2026-11-12

Status: incomplete acceptance; NOT production ready.

## Vault contract

Added worker-issued, short-lived HMAC approval covering user, chat, policy
revision, ordered values digest, expiration and synthetic-exercise flag.
Gateway validates integer ranges, ordering and limits before STORE; Vault verifies
approval and values/count/aggregate limits before encrypted storage. Scope is
restricted to the currently supported synthetic tenant; multi-tenant real-data
approval is not implemented. Existing Transit encryption, scoped lookup, TTL and
separate reveal credentials remain in place.

Proof-signing secret is a new independent local ignored file, mode 0600. Existing
credentials were not rotated. Proofs contain a digest, not plaintext; they must
not be logged. Replay prevention beyond scoped reuse and short expiry has not
been implemented or accepted.

General-value acceptance requires valid worker approval and either an explicitly
enabled synthetic-only exercise or the separate real-data flag. Both defaults
are false in Compose. With defaults, previous fixture restrictions remain.
Synthetic exercise flag is an operator declaration, NOT a classifier proving
that a value is fictional. Never enable it for uncontrolled users or input.
New arbitrary synthetic values have NOT passed the full acceptance matrix;
therefore general-value mode is NOT enabled in the running Native worker.

Vault/worker contract deployed, except final tenant restriction source change.
Frontend final controls are source-only: guarded build refused due to RAM/swap
pressure. Running health endpoint returned 200 after restoration; this is not
evidence of functional acceptance.

## Checks

- 108 component tests passed, including approval tampering and historical policy
  snapshot tests. Existing test suite does not cover full new Vault integration.
- One standalone Chromium PERSON MASK/reveal/continue/reload scenario passed.
- Worker publish changed REVIEW to BLOCK, old snapshot preserved REVIEW, rollback
  succeeded. Not a browser publication test.
- Multi-case Chromium runner still hangs; process isolated/stopped. No claim
  that remaining categories, multi-value or policy UI matrix passed.

## Required before real data

Keep `DLP_REAL_DATA_ENABLED=false` and `DLP_SYNTHETIC_EXERCISE=false`.
Complete independent security/privacy approval, tenant-bound approval contract,
replay analysis, concurrency/writer-permit revision tests, arbitrary synthetic
matrix, backend admin/auditor/reveal permission tests and browser publication
acceptance. Review configuration-body retention (policy versions contain dictionary
and regex text), log/trace redaction, backups, deletion/TTL, encryption lifecycle,
transport isolation, access reviews and incident response. Current test-only NLP
startup remains explicitly test-only; changing a flag alone is not real-data
authorization. No real LLM, OCR, PDF or file support was added.