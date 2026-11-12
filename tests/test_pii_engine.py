"""Real NLP tests run in the isolated pii image, not synthetic runtime."""
import pytest

pytest.importorskip('natasha')
pytest.importorskip('presidio_analyzer')
from ai_firewall.pii_engine import create_pipeline, inn_valid, snils_valid, luhn_valid
from ai_firewall.pii_policy import YAMLPolicy, inspect_object
from ai_firewall.detection import DetectorPipeline, PolicyContext, Action, DetectionUnavailable


@pytest.fixture(scope='module')
def pipeline(): return create_pipeline()


def test_checksums():
    assert inn_valid('7707083893') and inn_valid('500100732259')
    assert not inn_valid('7707083894') and not inn_valid('0000000000')
    assert snils_valid('112-233-445 95') and not snils_valid('112-233-445 96')
    assert luhn_valid('4111 1111 1111 1111') and not luhn_valid('4111 1111 1111 1112')


def test_real_unicode_and_cases(pipeline):
    text='😀 Письмо Иванову Ивану Ивановичу: robot@example.com'
    findings=[f for s in pipeline.inspect(text) for f in s.findings]
    # Natasha may split a full name into adjacent entities in this context.
    people=[f for f in findings if f.entity_type=='PERSON']
    assert people and min(f.start for f in people)==text.index('Иванову')
    assert max(f.end for f in people)==text.index(':')
    assert any(f.entity_type=='EMAIL_ADDRESS' for f in findings)


def test_policy_batch_block_review_no_vault(pipeline):
    policy=YAMLPolicy('/app/config/pii-policy-v1.yaml')
    combined=DetectorPipeline([*pipeline.detectors,*policy.detectors])
    context=PolicyContext('synthetic','synthetic','input',policy.version)
    assert inspect_object({'a':'robot@example.com','b':'SYNTHETIC_CORPORATE_SECRET'},combined,policy,context)[0]==Action.BLOCK
    assert inspect_object({'a':'SYNTHETIC_REVIEW_TEST'},combined,policy,context)[0]==Action.REVIEW
    assert inspect_object({'a':'robot@example.com'},combined,policy,context)[0]==Action.MASK
    assert inspect_object({'a':'Добрый день'},combined,policy,context)[0]==Action.ALLOW


def test_broken_model_fail_closed(pipeline):
    class Broken:
        name='broken-model'
        def detect(self,text,*,language): raise RuntimeError(text)
    with pytest.raises(DetectionUnavailable) as error:
        DetectorPipeline([*pipeline.detectors,Broken()]).inspect('SYNTHETIC_PRIVATE_INPUT')
    assert 'SYNTHETIC_PRIVATE_INPUT' not in str(error.value)


def test_bad_policy(tmp_path):
    p=tmp_path/'bad.yaml'; p.write_text('version: 1\nunknown: value')
    with pytest.raises(ValueError,match='invalid_pii_policy'): YAMLPolicy(p)