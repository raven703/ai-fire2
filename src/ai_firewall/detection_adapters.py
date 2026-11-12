"""Dependency-injected local adapters; no automatic model downloads/imports."""
import re
from collections.abc import Callable

from ai_firewall.detection import DetectionResult


class SyntheticAdapter:
    name = 'synthetic'

    def __init__(self, detector):
        self.detector = detector

    def detect(self, text, *, language):
        return [DetectionResult('SYNTHETIC_PII', m.start(), m.end(), 1.0, self.name)
                for m in self.detector.inspect(text)]


class PresidioAdapter:
    name = 'presidio'

    def __init__(self, local_analyzer):
        self.analyzer = local_analyzer

    def detect(self, text, *, language):
        return [DetectionResult(r.entity_type, r.start, r.end, r.score, self.name)
                for r in self.analyzer.analyze(text=text, language=language)]


class NatashaAdapter:
    name = 'natasha'

    def __init__(self, local_extract: Callable):
        # Integration supplies an initialized local Doc/segmenter/NER function
        # yielding (entity_type, start, end). Natasha spans have no calibrated
        # probability: use a configured conservative score, never fabricate 1.
        self.extract = local_extract

    def detect(self, text, *, language):
        if language != 'ru':
            raise ValueError('natasha_language_unsupported')
        return [DetectionResult(kind, start, end, .5, self.name)
                for kind, start, end in self.extract(text)]


class RegexChecksumDetector:
    """Explicit recognizer rules, e.g. locally reviewed Russian IDs/secrets.

    Validator is mandatory: pass an explicit lambda for formats without checksum.
    Rules must be reviewed for runtime bounds before deployment.
    """
    def __init__(self, name, entity_type, pattern, validator: Callable[[str], bool], confidence=.8):
        self.name, self.entity_type = name, entity_type
        self.pattern, self.validator = re.compile(pattern), validator
        self.confidence = confidence

    def detect(self, text, *, language):
        return [DetectionResult(self.entity_type, m.start(), m.end(), self.confidence, self.name)
                for m in self.pattern.finditer(text) if self.validator(m.group())]


class DictionaryDetector:
    def __init__(self, name, terms, entity_type='CORPORATE_TERM'):
        if not terms or any(not isinstance(term, str) or not term for term in terms):
            raise ValueError('nonempty_dictionary_required')
        self.name, self.entity_type = name, entity_type
        self.pattern = re.compile('|'.join(re.escape(t) for t in sorted(set(terms), key=lambda t: (-len(t), t))), re.IGNORECASE)

    def detect(self, text, *, language):
        return [DetectionResult(self.entity_type, m.start(), m.end(), 1.0, self.name)
                for m in self.pattern.finditer(text)]