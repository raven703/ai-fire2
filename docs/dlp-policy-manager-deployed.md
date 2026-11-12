# DLP Policy Manager deployed — 2026-11-12

Native original Open WebUI serves `/admin/dlp` on port 8089. Structured policy
controls are built and deployed. This report supersedes earlier source-only
checkpoint statements, not outstanding security acceptance limitations.

## Verified

- Guarded build succeeded after temporarily stopping project containers without
  deleting data. 7151 MiB available; 593 MiB inactive swap. Start swap ceiling
  increased to 1024 MiB; runtime additional-swap and RAM watchdog retained.
  BuildKit cache retained; Node heap remains 6144 MiB. Services restored.
- Fixed proxy credential variable (NATIVE_GATEWAY_KEY). Fixed changelog dismissal
  when protected mode rejects legacy preference writes; changelog suppressed in
  Native text-only mode.
- Chromium policy test passed in 38.70s: dedicated synthetic admin login,
  structured controls, draft/publication, new-chat BLOCK, UI rollback, REVIEW,
  auditor disabled controls and backend write denial, ordinary-user denial.
  Exact BLOCK/REVIEW bodies additionally checked through authenticated HTTP.
- Playwright reading a denied response body could hang. Tests avoid `.json()` on
  browser 403 responses, retain browser submission/status and independently assert
  verdict bodies. Separate browser processes bound individual MASK scenarios.
- Six new artificial-data browser cases passed: PERSON, contextual checksum-valid
  INN/SNILS, phone, BIC/account, mixed categories; reveal/continue/reload and Mock
  exclusion asserted. Mixed case checks each original independently.
- Component regression: 108 passed, 1 dependency deprecation warning.
- Named policy volume survived worker recreation: 64 audit entries, active pointer
  retained. Migrations remain additive, no existing data removed.

Evidence: `artifacts/dlp-policy-browser-final.log`, `dlp-arbitrary-{0..5}.log`,
`dlp-final-chat.log`, `dlp-deploy-regression.log`, `dlp-deploy-build.log`.

## Operator access and exercise mode

Two dedicated synthetic identities were provisioned using upstream Auths model
and password hashing. Existing accounts unchanged. Local credentials only:
`/home/user/ai-fire2/artifacts/.dlp-test-identities.json` (0600, ignored).
Never commit or print this file. Admin has upstream admin role; auditor remains
user, with its ID explicitly configured in DLP_AUDITOR_IDS. Preserve this setting
when recreating webui; default empty configuration removes auditor access.

The current isolated Native worker uses `compose.synthetic-exercise.yaml` as an
explicit opt-in overlay after `compose.native-vault-v2.yaml`. Without this overlay,
default synthetic-exercise flag is false. Only artificial data is authorized here.
This flag is an operator declaration, not proof that arbitrary input is fictional.
`DLP_REAL_DATA_ENABLED` remains false. Existing Transit, scoped TTL storage and
separate reveal permission/credentials remain in use.

## Limitations

Bare unlabeled INN/SNILS digits are not always classified: contextual labels are
required by current recognizers. Artificial checksum-valid values are not
guaranteed unassigned in reality; never contact generated phone numbers.
No broad real-data, multi-tenant, concurrency or production-readiness acceptance
is claimed. Existing approval replay, signed writer revision binding and sensitive
policy configuration retention reviews remain outstanding. See
`dlp-v2-integration-checkpoint.md` for real-data prerequisites. No real LLM/files.