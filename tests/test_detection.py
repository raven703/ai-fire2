import pytest

from ai_firewall.detection import (DetectionResult, DetectorPipeline, DetectionUnavailable,
    resolve_overlaps, MaskAllPolicy, PolicyContext, Action)
from ai_firewall.detection_adapters import (SyntheticAdapter, PresidioAdapter,
    NatashaAdapter, RegexChecksumDetector, DictionaryDetector)
from ai_firewall.services import SyntheticDetector


def test_synthetic_compatibility_and_unicode_offsets():
    text='Привет SYNTHETIC_PII_TEST_001'
    spans=DetectorPipeline([SyntheticAdapter(SyntheticDetector())]).inspect(text)
    assert text[spans[0].start:spans[0].end]=='SYNTHETIC_PII_TEST_001'


def test_overlap_union_retains_all_evidence():
    a=DetectionResult('A',0,8,.5,'one'); b=DetectionResult('B',2,4,.9,'two')
    c=DetectionResult('C',7,10,.7,'three')
    spans=resolve_overlaps([c,a,b,a],10)
    assert len(spans)==1 and spans[0].end==10 and len(spans[0].findings)==3


@pytest.mark.parametrize('result', [DetectionResult('X',-1,2,.5,'bad'),
    DetectionResult('X',0,9,.5,'bad'), DetectionResult('X',0,1,float('nan'),'bad')])
def test_invalid_results_fail_closed(result):
    class Bad:
        name='bad'
        def detect(self,text,*,language): return [result]
    with pytest.raises(DetectionUnavailable): DetectorPipeline([Bad()]).inspect('abc')


def test_failure_does_not_return_partial_findings():
    class Broken:
        name='broken'
        def detect(self,text,*,language): raise RuntimeError(text)
    with pytest.raises(DetectionUnavailable,match='mandatory_detection_failed'):
        DetectorPipeline([DictionaryDetector('dictionary',['secret']),Broken()]).inspect('secret')


def test_local_adapters_and_policy():
    class Analyzer:
        def analyze(self,*,text,language):
            assert language=='ru'
            return [type('R',(),dict(entity_type='PERSON',start=0,end=3,score=.8))()]
    detectors=[PresidioAdapter(Analyzer()), NatashaAdapter(lambda t:[('PER',0,3)]),
        RegexChecksumDetector('checksum','TEST_ID',r'\d+',lambda s: sum(map(int,s))%10==0),
        DictionaryDetector('secrets',['TEST_SECRET'],'SECRET')]
    spans=DetectorPipeline(detectors).inspect('Имя 55 TEST_SECRET')
    assert len(spans)==3 and len(spans[0].findings)==2
    context=PolicyContext('user','chat','input','v1')
    assert MaskAllPolicy().evaluate(spans,context).action==Action.MASK
    assert MaskAllPolicy().evaluate([],context).action==Action.ALLOW


def test_missing_or_duplicate_mandatory_detectors_denied():
    with pytest.raises(ValueError): DetectorPipeline([])
    d=DictionaryDetector('same',['test'])
    with pytest.raises(ValueError): DetectorPipeline([d,d])