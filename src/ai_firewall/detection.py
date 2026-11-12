"""Local detector/policy contracts. Not connected to the plaintext Vault.

Offsets are Python Unicode code-point offsets, end exclusive. Results never
carry matched plaintext. Adapters must load provisioned local models only.
"""
from dataclasses import dataclass
from enum import Enum
import math
from typing import Protocol, Sequence


@dataclass(frozen=True)
class DetectionResult:
    entity_type: str
    start: int
    end: int
    confidence: float
    source: str

    def validate(self, length: int):
        if (not self.entity_type or not self.source
                or type(self.start) is not int or type(self.end) is not int
                or not 0 <= self.start < self.end <= length
                or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError('invalid_detection_result')


class Detector(Protocol):
    name: str

    def detect(self, text: str, *, language: str) -> Sequence[DetectionResult]: ...


@dataclass(frozen=True)
class DetectionSpan:
    start: int
    end: int
    findings: tuple[DetectionResult, ...]


def resolve_overlaps(results: Sequence[DetectionResult], length: int) -> tuple[DetectionSpan, ...]:
    """Union overlapping ranges, retaining every detector's evidence.

    No high-confidence small span can expose the tail of a larger finding.
    Adjacent ranges are separate; duplicate evidence is deduplicated.
    """
    for result in results:
        result.validate(length)
    groups = []
    for result in sorted(set(results), key=lambda r: (r.start, r.end, r.source, r.entity_type, r.confidence)):
        if groups and result.start < groups[-1].end:
            old = groups.pop()
            groups.append(DetectionSpan(old.start, max(old.end, result.end), old.findings+(result,)))
        else:
            groups.append(DetectionSpan(result.start, result.end, (result,)))
    return tuple(groups)


class DetectionUnavailable(RuntimeError):
    pass


class DetectorPipeline:
    def __init__(self, detectors: Sequence[Detector]):
        if not detectors or len({d.name for d in detectors}) != len(detectors):
            raise ValueError('mandatory_detectors_required_with_unique_names')
        self.detectors = tuple(detectors)

    def inspect(self, text: str, *, language: str = 'ru') -> tuple[DetectionSpan, ...]:
        if not isinstance(text, str):
            raise TypeError('text_required')
        results = []
        try:
            for detector in self.detectors:
                findings = detector.detect(text, language=language)
                for finding in findings:
                    if finding.source != detector.name:
                        raise ValueError('detector_source_mismatch')
                    finding.validate(len(text))
                    results.append(finding)
            return resolve_overlaps(results, len(text))
        except Exception:
            # No detector exception or plaintext may reach application logs.
            raise DetectionUnavailable('mandatory_detection_failed') from None


class Action(str, Enum):
    ALLOW = 'ALLOW'
    MASK = 'MASK'
    BLOCK = 'BLOCK'
    REVIEW = 'REVIEW'


@dataclass(frozen=True)
class PolicyContext:
    user: str
    chat: str
    operation: str
    policy_version: str


@dataclass(frozen=True)
class PolicyDecision:
    action: Action
    spans: tuple[DetectionSpan, ...]
    policy_version: str


class PolicyEngine(Protocol):
    def evaluate(self, spans: Sequence[DetectionSpan], context: PolicyContext) -> PolicyDecision: ...


class MaskAllPolicy:
    """Baseline only; REVIEW/BLOCK policy implementations must precede storage."""
    def evaluate(self, spans: Sequence[DetectionSpan], context: PolicyContext) -> PolicyDecision:
        if not context.policy_version or context.operation not in {'input', 'output', 'chat-write', 'model-request'}:
            raise ValueError('invalid_policy_context')
        return PolicyDecision(Action.MASK if spans else Action.ALLOW, tuple(spans), context.policy_version)