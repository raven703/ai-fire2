# DLP Detection Engine v2 verification

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