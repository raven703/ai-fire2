# DLP Policy Manager verification

Status: **SOURCE PROTOTYPE, NOT DEPLOYED / NOT ACCEPTED**.

## 2026-11-12 integration checkpoint (not acceptance)

- Initial policy page built and deployed; final structured-controls changes are
  source-only. Final build refused twice by existing memory watchdog (last:
  available 6996 MiB < 7040; swap 592 MiB > 512). Limits were not bypassed.
- Administrative POST added to mandatory Native allowlist. Two existing ordinary
  identities returned 403. Existing admin credentials were not available to this
  run; no passwords or roles were changed and no admin token was forged.
- NLP policy SQLite moved to named `native-policy-data` volume. Schema creation
  is additive (`CREATE TABLE IF NOT EXISTS`); existing versions are retained.
- Worker snapshots support historical revision selection; NativeInspector pins
  a revision per instance and rejects changed revisions. Gateway forwards revision;
  stored messages include revision metadata. Full concurrent lifecycle acceptance
  and signed binding of revision metadata to writer permits remain outstanding.
- Deployed worker integration: draft + publish changed REVIEW to BLOCK; explicit
  old revision retained REVIEW; rollback succeeded in finally. This is a worker
  integration check, NOT UI or end-to-end policy publication acceptance.
- Final component regression: 108 passed, 1 dependency deprecation warning
  (`artifacts/policy-regression-final.log`).
- Chromium: PERSON MASK/reveal/continue/reload passed (29.80s), including existing
  Mock plaintext-exclusion assertion. Multi-case run hung after first dot and was
  explicitly stopped; remaining scenarios NOT accepted.
- Runtime regex timeout already exists in BoundedRegex (50ms). Validation now
  permits bounded-runtime baseline editing instead of rejecting its `+` operator.
- Final source includes structured action/threshold/enabled controls, dictionary
  and regex fields, auditor read-only fieldset and admin navigation. Not rebuilt.

The earlier prototype notes below are historical; outstanding items are not
superseded unless explicitly verified above.

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