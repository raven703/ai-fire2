# Local PII Detection Engine foundation

This is an unconnected, tested interface foundation, NOT real-PII readiness.
Production Gateway still uses the unchanged SyntheticDetector. No real detector
is connected to the plaintext Vault, no new dependency is installed, and no
model download or external inference is performed.

## Implemented contracts

- `DetectionResult`: entity type, Unicode code-point start/end (end exclusive),
  finite confidence [0,1], detector source. No plaintext in results.
- Mandatory `DetectorPipeline`: unique named detectors; failure, invalid offsets,
  invalid scores or source mismatch aborts the whole inspection. No partial ALLOW.
- Overlap resolver unions intersecting ranges transitively and retains evidence;
  this avoids revealing tails when a smaller high-confidence span overlaps a
  larger finding. Adjacent spans remain separate. Duplicates are removed.
- Dependency-injected adapters: SyntheticDetector, local Presidio analyzer,
  local Natasha extraction function, regex plus mandatory validator/checksum,
  and escaped corporate/secret dictionary recognizers. Regex rules/checksum
  algorithms for actual Russian identifiers are intentionally not shipped yet.
- PolicyEngine protocol: complete spans plus scoped context/policy version yields
  ALLOW/MASK/BLOCK/REVIEW. Baseline MaskAllPolicy is only a contract example.
  Policy evaluation must finish for the entire batch before any storage side
  effect; errors/BLOCK/REVIEW do not issue an admission. Existing Gateway batch
  policy remains authoritative until a separately tested migration.

## Immediate implementation sequence

1. Pin compatible Presidio/Natasha and NLP dependencies in a separate local
   detector image; check licenses and provision immutable local model artifacts.
   Disable implicit downloads and reject startup when models are missing.
2. Implement concrete Natasha Doc/segmenter/NER extraction and local Presidio
   analyzer factory. Validate Unicode offsets (including emoji and combining
   characters). Natasha's adapter score .5 is an explicit uncalibrated placeholder
   confidence, not a measured probability; calibrate before enforcement.
3. Add reviewed Russian regex/checksum recognizers (INN/SNILS, etc.), separate
   format validity from contextual entity confidence. Use synthetic/generated
   corpora only, measure precision/recall, and bound regex runtime/text lengths.
4. Add local versioned secret patterns/corporate dictionaries and explicit entity
   action policy. Define cross-detector priority/confidence rules without losing
   union masking coverage. Validate BLOCK precedence before Vault calls.
5. Add per-detector deadlines/isolation, concurrency limits, health/readiness and
   circuit-breaker behavior. Current synchronous pipeline has no timeout manager;
   it is not suitable for unbounded model execution on an async request loop.
6. Replace plaintext synthetic Vault with a separately accepted encrypted data
   lifecycle, retention and access-control design BEFORE permitting real PII.
   Only then connect the pipeline through a synthetic-only integration flag and
   repeat full native E2E/fault/replay/leak tests before expanding data scope.

Adapter tests use fake local engines to validate contracts, NOT actual
Presidio/Natasha quality, model loading, runtime or language coverage.