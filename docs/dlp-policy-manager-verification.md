# DLP Policy Manager verification

Status: **SOURCE PROTOTYPE, NOT DEPLOYED / NOT ACCEPTED**.

Implemented source: original Svelte route `/admin/dlp`, JSON policy editing,
draft/publish/history/rollback; SQLite transactional active pointer and hash-only
audit entries; upstream authenticated backend proxy with admin writes, explicit
operator-configured auditor read access and ordinary-user denial. No separate
frontend. Source prototype must not be advertised as available on 8089.

Executed targeted tests: **4 passed** (policy store and existing PII service).
Draft isolation, publication conflict, rollback and bounded regex rejection
tested. Regex editing currently rejects unbounded quantifiers/lookarounds; this
also prevents editing existing baseline patterns without replacement. Incomplete
UX, not a final regex validator.

Outstanding before deployment:
- Native middleware allowlist and configured authenticated NLP connectivity.
- Persistent policy storage mount (default /tmp is NOT durable).
- Whole-message policy revision pinning across Gateway/NLP/write/output.
- Stronger dictionary/regex content restrictions: audit entries are hash-only,
  but version bodies contain configuration values and can contain sensitive text.
- Separate auditor frontend navigation and RBAC API integration tests.
- Dedicated enable/disable controls, thresholds/category UI rather than raw JSON.
- Full build, Chromium admin publish/new-message/rollback/user-denial checks.

Real-data mode NOT enabled: generated fixture restriction remains in deployed
Vault. Existing production-readiness and Vault acceptance limitations unchanged.