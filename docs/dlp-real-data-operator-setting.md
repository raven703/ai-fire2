# Explicit operator setting: general MASK admission enabled

At the operator's explicit request, compose.vault-v2.yaml now persists
`DLP_REAL_DATA_ENABLED=true`. The running Vault reports true. Native worker was
recreated without the synthetic-exercise overlay and reports
`DLP_SYNTHETIC_EXERCISE=false`. Do not automatically revert this operator setting.
The synthetic-exercise overlay is no longer part of the current deployment.

Validation: original Chromium artificial PERSON scenario passed MASK, reveal,
continue, reload and Mock exclusion (1 passed in 15.24s), with synthetic-exercise
disabled. Native health 200. Evidence: artifacts/real-data-mode-smoke.log.
No real personal data was used in this verification.

This changes admission configuration only, not production/security acceptance.
Existing test-only worker configuration, synthetic tenant/policy names, incomplete
multi-tenant acceptance, approval replay analysis and writer-version binding
limitations remain. Encryption, authentication, signed MASK approval, TTL,
separate reveal credentials and mandatory DLP were not disabled or modified.
Earlier reports describing real-data flag as false are historical and superseded
by this explicit setting; their unresolved safety limitations remain applicable.