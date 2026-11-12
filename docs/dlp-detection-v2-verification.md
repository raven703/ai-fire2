# DLP Detection Engine v2 verification

## MASK/reveal continuation root cause and fix

Canonical random V2 tokens sometimes contain digit substrings passing Luhn.
Reproduction: repeated first/second Native turns failed on iteration 15;
direct opaque-token NLP probe returned MASK/CREDIT_CARD. Gateway then attempted
to store a token substring, rejected by synthetic Vault membership, surfacing
native_inspection_denied. Fix: suppress findings wholly inside exact canonical
`[V2_[a-f0-9]{64}]` ranges only. Surrounding text and malformed tokens still scan.
No timeout increased, writer permits and Vault checks retained.

Deployed updated NLP and incremental Native backend. Native inspector logs only
generated correlation ID, operation, status, duration and gateway source.
Correlation header propagated to Gateway; full distributed tracing not claimed.

Actual standalone Chromium: **PASS** login, specified INN MASK, reveal, exact
second message “Продолжим разговор”, successful completion, Mock original absence,
reload with no displayed original. This run used bounded Playwright operations.
Pytest multi-case runner still stalls and was stopped: unresolved test harness
hang, not claimed fixed. New per-operation bounds alone did not solve it.

Targeted regression: **22 passed** including opaque-token and detector units.
Full regression attempt: **103 passed, 1 failed**, global Mock capture mismatch;
concurrent leftover runner may have interfered, root cause not established.
Policy Manager remains NOT IMPLEMENTED; no claim of completion.

## Latest integration attempt

Nonbrowser regression rerun: **103 passed**, 10.39 seconds, one dependency
warning (`artifacts/v2-current-regression.log`). The previous failed assertion
compared a global Mock last-request capture, not Vault same-scope token reuse.
Targeted rerun passed unchanged. Root cause of historical capture mismatch is
not proven; no token logic or assertion was disabled.

Multi-category browser test split into eight independent parametrized cases,
with action/category, reveal, reload and masked-history assertions. Initial run:
**1 passed, 1 failed**, continuation returned 503. Follow-up run stalled after
first passed case and was stopped. These are not accepted E2E results.
Do not claim integration complete. Policy Manager remains unimplemented.

User requested arbitrary real-data input; current deployment still enforces
generated-fixture membership. No unrestricted real-PII enablement was deployed.

Status: **PARTIAL, backend deployed; not final acceptance**. Vault debt is
nonblocking. No production-readiness claim.

Implemented Presidio/Natasha plus local OGRN/OGRNIP checksums, contextual
birthdays/calendar validation and addresses, JWT structural checks (not signature
verification), Bearer, API/cloud-key signatures, configuration passwords,
credential-bearing database URIs and PEM/OpenSSH private-key blocks. Existing
INN/SNILS/card/account checks remain. Dictionaries provide corporate BLOCK and
ambiguous internal-use/contract REVIEW; no semantic classifier is claimed.

Vault accepts generated fixture membership across categories, not arbitrary real
values. Encryption, TTL and scope unchanged. Generated valid identifiers are not
guaranteed unassigned nationally; never contact generated phone numbers.

## Executed results

- New units: **2 passed**.
- Corpus: 1300 development + 1300 holdout, separate random seeds, shared templates.
  This is **not independently authored holdout**. Precision/recall/F1 1.0 and
  FPR/FNR 0 on 13 measured categories in this narrow template distribution.
  Secret/adversarial/invalid/Unicode/false-BLOCK coverage is insufficient.
- Metrics/corpus: ignored `artifacts/detection-v2/`; generator/evaluator:
  `scripts/evaluate-detection-v2.py`, executed offline in `ai-fire2-pii:v2`.
- Actual authenticated Native HTTP: 12 generated category scenarios returned 200
  with no lifecycle errors, including account+BIC.
- Chromium multi-category smoke stalled and was stopped: **NOT PASSED**.
  Separate original-composer one-message check returned 200. New-category
  reveal/continued-history visual acceptance remains NOT TESTED.
- Regression: **102 passed, 1 failed**: existing integration token-reuse assertion
  in `test_mask_real_database_and_display_only`. Not clean.
- PII image v2 and generated-membership Vault deployed; no frontend changes.
  Policy Manager not started.

## Reproduce using generated fixtures on localhost:8089

```text
Иванов Иван Иванович
ИНН: 9921602301
СНИЛС: 99920834984
Телефон: +7 (999) 441-91-41
БИК: 049993894 р/с: 40702593805366195758
ОГРН: 9629541792750
дата рождения: 01.01.1990
api_key=sk-test-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SYNTHETIC_CORPORATE_SECRET
для внутреннего использования
```

First seven expect MASK; fake key/corporate marker BLOCK; last REVIEW. Rejection
UI may remain generic. Name casing/inflection remains model-dependent. Arbitrary
values deny at the Vault boundary. Do not enter real personal data or secrets.