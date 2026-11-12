# PII engine v1 — integrated test contour, November 12, 2026

## Integration acceptance update (supersedes partial status below)

Original WebUI at `http://127.0.0.1:8089/` now runs the explicit test overlay.
Mock is left in `dlp-debug`. No frontend changes. Deployment:

```sh
cd /home/user/ai-fire2
docker compose -f compose.native.yaml -f compose.native-core.yaml -f compose.pii-test.yaml up -d --no-build
```

Examples: `Привет, это проверка.` → ALLOW;
`Проверка SYNTHETIC_PII_DEMO_123` → MASK/SYNTHETIC_PII;
`Тестовый получатель: Иванов Иван Иванович.` → MASK/PERSON;
`SYNTHETIC_BLOCK_DEMO` → BLOCK; `SYNTHETIC_REVIEW_DEMO` → REVIEW.

**Synthetic tests only. Do not enter real personal data.** Worker masks real
recognizer fixtures irreversibly as `[DLP_REDACTED]`, without a Vault client.
Gateway receives its full verdict before synthetic admission/Vault operations.
Existing plaintext Vault validation remains synthetic-only. This is NOT a
production MASK/reveal integration. Backend composes diagnostics from authenticated
Gateway results; Mock never infers DLP action. No metadata/raw originals in prompt.
Provider output is checked even when replaced by diagnostic output; diagnostic
output also follows normal output admission/writer permit. BLOCK/REVIEW precedes
Mock. Debug preinspection is request-local and checks ownership/permission.

### Models, isolation and versions

Resolved transitive versions committed in `config/pii-requirements.lock`.
Natasha bundled embedding/NER/morph/syntax hashes in `config/pii-models.sha256`
are checked at worker startup. No implicit startup downloads. Models load once;
readiness performs warmup. Worker: 768 MiB, 1 CPU, 64 PIDs, read-only filesystem,
internal network, one model execution thread. Gateway dependency timeout 5 s;
Native inspection timeout 10 s. No timeout fallback. Running timed-out computation
is not forcibly cancelled; subsequent admissions still fail closed. Custom regex
uses 50 ms timeout; policy file/rule/dictionary sizes are bounded. Unknown category
REVIEW. Policy version `synthetic-evaluation-v1`.

Version lock is not wheel-hash locking; Python base/local incremental Native parent
are tags, so this is not a fully hermetic build claim. Backend-only incremental
image preserves the verified UI. Builds/Chromium executed sequentially.

### Quality update

Initial phone FP were generic Presidio guesses for numeric IDs. Both Presidio and
Russian rules now require valid 11-digit RU numbers using local phonenumbers
metadata. Old four FP disappeared. Adjacent model-confirmed PER spans are joined.
NFC per combining cluster maps coordinates back to original code points; emoji
and decomposed Cyrillic tests pass. Not universal homoglyph normalization.

New frozen holdout-style corpus: **58 samples, 27 negatives**. Authored by the
implementer after the general rule change, not independently reviewed. No rules
were tuned after its evaluation. Exact-span scores:

| Category | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| PERSON | 7 | 0 | 0 | 1 | 1 | 1 |
| PHONE_NUMBER | 5 | 1 | 0 | .833 | 1 | .909 |
| EMAIL_ADDRESS | 3 | 0 | 0 | 1 | 1 | 1 |
| IP_ADDRESS | 2 | 1 | 1 | .667 | .667 | .667 |
| RU_PASSPORT | 2 | 0 | 0 | 1 | 1 | 1 |
| LOCATION | 1 | 1 | 0 | .5 | 1 | .667 |
| CREDIT_CARD | 1 | 0 | 0 | 1 | 1 | 1 |
| RU_BIC | 2 | 0 | 0 | 1 | 1 | 1 |
| RU_INN | 3 | 0 | 0 | 1 | 1 | 1 |
| RU_SNILS | 3 | 0 | 0 | 1 | 1 | 1 |
| ORGANIZATION | 1 | 0 | 0 | 1 | 1 | 1 |
| RU_BANK_ACCOUNT | 1 | 0 | 0 | 1 | 1 | 1 |

False BLOCK **0/27** under shipped policy. Phone is MASK, not BLOCK: this does
not validate a mandatory phone-blocking policy. Confidence remains heuristic,
not calibrated, thresholds category-level rather than per-detector. General
accuracy is not perfect; small counts do not establish production quality.

Offline measurement: startup 1.645 s, mean 3.374 ms, max 71.274 ms, peak RSS
263.80 MiB. Running worker observed 228.8 MiB/768 MiB, Native WebUI 818 MiB.
Not a concurrency/load benchmark.

### Executed acceptance

- Full nonbrowser regression with NLP, SQLAlchemy, fork hooks and live POC
  integration: **100 passed, no skips**, one existing warning.
- Final original Chromium suite: **6 passed, 3 skipped** (explicit faults).
- NLP model failure through composer: separately **1 passed**; 503, Mock unchanged,
  canary absent DB/WAL and local/session storage.
- Gateway outage through composer: separately **1 passed**.
- Gateway killed after Mock received request, before output DLP: separately
  **1 passed**, clean input retained, no assistant write/display.
- Actual Chat/ChatMessage/nonce script: PASS, including live input/output MASK,
  stale/foreign denial, BLOCK/outage rollback, DB sweep.
- Debug Chromium covers ALLOW, synthetic MASK/category, real PERSON fixture,
  BLOCK/REVIEW with unchanged Mock capture, multi-turn/reload, Mock requests,
  DB/WAL and local/session storage canary absence.
- Existing acceptance Chromium covers two verified users plus IndexedDB,
  CacheStorage and Service Workers using localhost secure context.
- Service logs webui/gateway/mock/vault: tested raw canary prefixes and fictional
  FIO absent. Offline evaluation stderr empty. Not a universal leak proof.

Initial browser/fault runs before WebUI readiness failed connection setup; reruns
passed. Output-outage initially exposed error classification hiding DLP failure
as model failure; sanitized HTTPException preservation fixed, rerun passed.
Non-Playwright full-suite collection initially included browser files; explicit
browser exclusions corrected execution. Baseline image separately achieved
92 passed/3 skips; complete NLP-capable image achieved 100 passed above.

Ignored evidence: `artifacts/pii-all-regression.log`,
`artifacts/pii-native-browser-final.log`, `artifacts/pii-nlp-fault.log`,
`artifacts/pii-gateway-fault.log`, `artifacts/native-output-outage.log`,
`artifacts/pii-native-models.log`, `artifacts/pii-heldout-metrics.json`,
`artifacts/pii-service-logs.log`, `artifacts/pii-dlp-debug.png`.

Remaining: larger independently reviewed benchmark, phone/IP FP work, calibrated
scores, protected Vault encryption/access/retention acceptance, stronger process
supervision/load tests, hashed dependency provisioning. POC/history/volumes/fork
preserved. No external LLM, admin UI, OCR/RAG/file routes or remote push.

---

## Historical partial implementation record (superseded where noted above)

**Not accepted as a completed v1. No production/real-PII safety claim.**

## Executed

Built `ai-fire2-pii:v1` sequentially using `/home/user/ai-fire2/docker/Dockerfile.pii`.
Installed real presidio-analyzer 2.2.360, natasha 1.6.0, spaCy 3.8.11,
PyYAML 6.0.3. Natasha uses the bundled NewsEmbedding/NewsNERTagger artifacts;
spaCy is explicitly a blank Russian tokenizer, not pretrained NER.
Runtime analysis was executed with Docker `--network none`. Email suffix
validation uses tldextract's bundled snapshot with network URLs disabled.
No downloads occur in the engine factory. Models are initialized once per
pipeline instance; there is not yet a deployed detector service lifecycle.
Resolved package inventory is in ignored `artifacts/pii-environment.txt`.
Transitive dependencies and model hashes still require a committed lock manifest.

Real pipeline: Presidio email/phone/card/IP + Natasha PER/ORG/LOC + Russian
formal recognizers. INN and SNILS checksums, Luhn, context-required passport,
BIC structural format and BIC-dependent settlement account checksum implemented.
BIC format is not a bank-directory verification. Passport format is not document
authenticity verification. Account implementation does not cover correspondent
account rules. Recognizers operate on original Unicode code-point offsets;
normalization/remapping and homoglyph handling remain unimplemented.

YAML policy supports category actions, thresholds, BLOCK > REVIEW > MASK > ALLOW,
dictionary and regex detectors. Unknown categories REVIEW. Full-object harness
has no Vault callback or persistence dependency. It is NOT Gateway integration.
Thresholds are category-level, not per-detector; .85 Natasha scores are heuristic,
not calibrated probabilities. Regex timeout/resource isolation remains missing.

## Measurements and quality

24 manually annotated synthetic examples, exact entity/span matching, one run:
startup 1.537 s; mean analysis 5.529 ms; maximum 57.325 ms; peak RSS 264.22 MiB.
These are small-sample process measurements, not service load benchmarks.

| Category | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| PERSON | 4 | 0 | 0 | 1 | 1 | 1 |
| EMAIL_ADDRESS | 1 | 0 | 0 | 1 | 1 | 1 |
| PHONE_NUMBER | 2 | 4 | 0 | .333 | 1 | .5 |
| RU_INN | 2 | 0 | 0 | 1 | 1 | 1 |
| RU_SNILS | 1 | 0 | 0 | 1 | 1 | 1 |
| RU_PASSPORT | 1 | 0 | 0 | 1 | 1 | 1 |
| CREDIT_CARD | 1 | 0 | 0 | 1 | 1 | 1 |
| IP_ADDRESS | 1 | 0 | 0 | 1 | 1 | 1 |
| RU_BIC | 1 | 0 | 0 | 1 | 1 | 1 |
| LOCATION | 0 | 1 | 0 | 0 | undefined | 0 |

This is an initial smoke corpus, NOT an independent held-out quality benchmark.
No general claim of perfect detection is justified. Bank accounts/organizations
are not covered by this evaluation. False blocking rate has not been measured.
An additional Unicode/case test exposed Natasha splitting a full name in a
different context; test checks bounds without pretending exact-span success.

Real-engine plus existing detector unit tests: **13 passed**. Includes
BLOCK/REVIEW batch evaluation, invalid YAML and mandatory model exception
sanitization. Evaluation stderr was empty. This is not a comprehensive leak audit.

Regression in the isolated image: **57 passed, 41 skipped**, one existing
Starlette warning. Missing optional integration prerequisites mean this does NOT
replace the prior 92-test regression acceptance. Initial run without TEST_KEY
failed one service test; rerun with a synthetic TEST_KEY passed.

## Unfinished acceptance

- Gateway service integration/readiness/timeouts/resource isolation.
- Strict bounded policy schemas, per-detector thresholds and calibrated scores.
- Normalization with source-coordinate mapping, robust mixed-script handling.
- Independent larger labeled corpus, bank-account tests, false-block metrics.
- Committed dependency/model hash lock and reproducible artifact provisioning.
- `dlp-debug`, trusted metadata lifecycle and Chromium ALLOW/MASK/BLOCK tests.
- Full Native regression, Chromium, fault and leak/replay re-execution.

Existing Native and POC containers remained running; native WebUI reported
healthy during inspection. No existing runtime, frontend, Vault, database,
volume, history or fork files were modified. Plaintext Vault remains synthetic-only.
No external LLM used, remote push performed, or acceptance commit created.