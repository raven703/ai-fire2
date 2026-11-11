import asyncio
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ai_firewall.admission import Admission
from ai_firewall.batch import inspect_batch
from ai_firewall.protocol import canonical, harden
from ai_firewall.services import SyntheticDetector, gateway_app


def run(fields, detector=None, operation='input'):
    writes = []

    async def store(value, user, chat):
        writes.append(value)
        return '[PII_' + 'a' * 48 + ']'

    data = dict(user=str(uuid.uuid4()), chat=str(uuid.uuid4()), operation=operation,
                revision='0' * 64, fields=fields)
    admission = Admission(b'a' * 32, 'synthetic-v2')
    return data, writes, admission, lambda: asyncio.run(inspect_batch(data, detector or SyntheticDetector(), store, admission))


@pytest.mark.parametrize('marker', ['SYNTHETIC_BLOCK_DENY', 'SYNTHETIC_REVIEW_PENDING'])
def test_batch_final_verdict_precedes_all_vault_writes(marker):
    data, writes, _, invoke = run({'first': 'SYNTHETIC_PII_FIRST', 'last': marker})
    with pytest.raises(HTTPException) as error:
        invoke()
    assert error.value.status_code == 403
    assert writes == []


def test_detector_failure_in_later_field_prevents_vault_writes():
    class Broken:
        def inspect(self, value):
            if value == 'fail':
                raise RuntimeError('private')
            return SyntheticDetector().inspect(value)
    _, writes, _, invoke = run({'first': 'SYNTHETIC_PII_FIRST', 'last': 'fail'}, Broken())
    with pytest.raises(HTTPException) as error:
        invoke()
    assert error.value.status_code == 503
    assert not writes


def test_batch_mask_exact_scoped_receipt():
    data, writes, admission, invoke = run({'first': 'hello SYNTHETIC_PII_FIRST', 'last': 'safe'})
    result = invoke()
    assert result['action'] == 'MASK'
    assert writes == ['SYNTHETIC_PII_FIRST']
    assert 'SYNTHETIC_PII_' not in str(result)
    payload = result['payload']
    assert admission.verify(result['admission'], canonical(payload), data['user'], 'input')
    assert not admission.verify(result['admission'], canonical(payload), str(uuid.uuid4()), 'input')
    payload['revision'] = '1' * 64
    assert not admission.verify(result['admission'], canonical(payload), data['user'], 'input')


@pytest.mark.parametrize('fields', [[], {}, {'x': {'nested': 'SYNTHETIC_PII_X'}}, {'bad/name': 'safe'}])
def test_batch_strict_schema(fields):
    _, writes, _, invoke = run(fields)
    with pytest.raises(HTTPException):
        invoke()
    assert not writes


def test_batch_requires_service_auth(monkeypatch):
    monkeypatch.setenv('ADMISSION_KEY', 'a' * 32)
    monkeypatch.setenv('NATIVE_GATEWAY_KEY', 'b' * 32)
    client = TestClient(harden(gateway_app()))
    assert client.post('/native/inspect', json={}).status_code == 403
    assert client.post('/native/inspect', json={}, headers={'Authorization': 'Bearer ' + 'b' * 32}).status_code == 400