import asyncio
import uuid

import httpx
import pytest
from fastapi import HTTPException

from ai_firewall.admission import Admission
from ai_firewall.native_client import NativeInspector, revision
from ai_firewall.protocol import canonical


def invoke(handler):
    inspector = NativeInspector('http://gateway', 's' * 32, 'a' * 32,
                                transport=httpx.MockTransport(handler))
    return asyncio.run(inspector.inspect({'content': 'safe'}, str(uuid.uuid4()),
                                        str(uuid.uuid4()), 'input', revision([])))


def test_valid_exact_batch_receipt():
    def handler(request):
        import json
        payload = json.loads(request.content)
        return httpx.Response(200, json={'payload': payload, 'action': 'ALLOW',
            'admission': Admission(b'a' * 32, 'synthetic-v2').issue(canonical(payload), payload['user'], 'input')})
    assert invoke(handler) == {'content': 'safe'}


@pytest.mark.parametrize('mode', ['bad_signature', 'wrong_chat', 'wrong_revision', 'extra_field', 'review'])
def test_reject_invalid_receipt(mode):
    def handler(request):
        import json
        payload = json.loads(request.content)
        if mode == 'wrong_chat':
            payload['chat'] = str(uuid.uuid4())
        if mode == 'wrong_revision':
            payload['revision'] = '1' * 64
        if mode == 'extra_field':
            payload['fields']['injected'] = 'text'
        token = Admission(b'a' * 32, 'synthetic-v2').issue(canonical(payload), payload['user'], 'input')
        return httpx.Response(200, json={'payload': payload, 'action': 'REVIEW' if mode == 'review' else 'ALLOW',
                                       'admission': 'broken' if mode == 'bad_signature' else token})
    with pytest.raises(HTTPException) as error:
        invoke(handler)
    assert error.value.status_code == 503


@pytest.mark.parametrize('status', [403, 500, 503])
def test_dependency_denial(status):
    with pytest.raises(HTTPException) as error:
        invoke(lambda request: httpx.Response(status))
    assert error.value.status_code == (403 if status == 403 else 503)


def test_network_outage():
    def handler(request):
        raise httpx.ConnectError('unavailable')
    with pytest.raises(HTTPException) as error:
        invoke(handler)
    assert error.value.status_code == 503