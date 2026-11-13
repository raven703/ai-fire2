# PERSON casing improvement — deployed

Installed Natasha 1.6.0 was tested directly. Upstream API documentation reviewed:
https://github.com/natasha/natasha (NamesExtractor, MorphVocab, news-domain caveat).

On the ten requested positive cases, original NER found PERSON in 6/10; lowercase
full name, uppercase full name, lowercase command and declined female name were
missed. NamesExtractor found components in all ten but split lowercase surnames
and double surnames; accepting lone matches would also flag ordinary words.
The added dictionary-morphology pass covers all ten complete ranges in unit
tests. Original NER remains on unchanged text; overlapping evidence is unioned.

Implementation: NamesExtractor(MorphVocab), reject lone facts, casefold only for
dictionary lookup, known Name/Surn/Patr combinations, hyphenated surnames and
initials. No title-case conversion. Original offsets retained and existing NFC
cluster mapping reused. Existing PERSON action/threshold policy applies; no new
frontend or settings. Confidence is heuristic (.85/.9/.95), not calibrated.
Unknown/ambiguous lone words are not automatically assigned REVIEW or PERSON.

pymorphy2 compatibility: installed Python 3.12 lacks getargspec and installed
environment lacks pkg_resources. Explicit installed dictionary path and local
BaseAnalyzerUnit parameter introspection adaptation enable MorphVocab; no new
NLP dependency or global inspect replacement. Bounded 4096-token morphology
cache contains lexical tokens in memory only; no raw content logging added.

## Independent small evaluation

Frozen after implementation, 12 positive / 12 negative examples, separate names
and sentences from development cases. No rule tuning after evaluation.
Document-level PERSON presence metric (NOT exact-span benchmark):

| Method | TP | FP | FN | TN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original NER | 6 | 0 | 6 | 12 | 1.000 | .500 | .667 |
| Combined | 11 | 0 | 1 | 12 | 1.000 | .917 | .957 |

Remaining FN: rare lowercase non-Russian dictionary pair (case 11). Small sample
does not justify universal accuracy claims. Morphological ambiguity can cause
false positives on larger corpora; single names remain dependent on original NER.
Comparison output uses case IDs and bounds, not runtime user data.

## Executed checks

- 20 added unit cases: original full spans, lower/upper/mixed, inflections,
  hyphen, initials, whitespace, decomposed Unicode, negatives, canonical V2.
- Full component regression: 128 passed, one dependency warning.
- Five separate Chromium cases: title/lower/upper full name, lowercase interview
  command and `петровой анне сергеевне`: all passed MASK/reveal/continue/reload,
  canonical response and Mock exclusion; no response publication error.
- Ordinary-text Chromium ALLOW passed; new no-match wording deployed.
- Policy publication/rollback/RBAC Chromium passed (61.47s); existing settings
  continue applying without policy schema changes.
- NLP image and cached Native backend layer rebuilt/deployed. Health 200.
- DLP_REAL_DATA_ENABLED remains true as explicitly requested by operator;
  worker synthetic-exercise false. Fail-closed/output DLP/permits unchanged.

Evidence: artifacts/person-method-comparison.log, person-quality.log,
person-unit.log, person-regression.log, person-browser-{0..4}.log,
person-allow-browser.log, person-policy-browser.log.
Browser asserts returned canonical history and reload behavior, not a full SQL
forensic scan. Existing production/security acceptance limitations remain.