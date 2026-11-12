import os
import pytest
pytest.importorskip('natasha')
from fastapi.testclient import TestClient


def test_real_worker_mask_block_review_failure(monkeypatch):
    monkeypatch.setenv('PII_TEST_ONLY','true')
    monkeypatch.setenv('NATIVE_GATEWAY_KEY','k'*32)
    from ai_firewall.pii_service import app
    headers={'Authorization':'Bearer '+'k'*32}
    with TestClient(app) as client:
        assert client.get('/health').json()['ready']
        def post(value): return client.post('/inspect',headers=headers,json={'fields':{'x':value},'operation':'input'})
        result=post('Почта robot@example.com').json()
        assert result['action']=='MASK' and 'robot@example.com' not in str(result)
        assert 'EMAIL_ADDRESS' in result['categories']
        assert post('SYNTHETIC_CORPORATE_SECRET').status_code==403
        assert post('SYNTHETIC_REVIEW_TEST').status_code==403
        monkeypatch.setenv('PII_MODEL_FAILURE','1')
        result=post('PRIVATE_CANARY')
        assert result.status_code==503 and 'PRIVATE_CANARY' not in result.text


def test_normalization_offsets():
    from ai_firewall.pii_engine import NormalizedDetector
    from ai_firewall.detection import DetectionResult
    class Example:
        name='example'
        def detect(self,text,*,language):
            start=text.index('ё')
            return [DetectionResult('PERSON',start,start+1,.8,self.name)]
    text='😀 е\u0308!'
    finding=NormalizedDetector(Example()).detect(text,language='ru')[0]
    assert text[finding.start:finding.end]=='е\u0308'