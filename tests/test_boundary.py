import secrets

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from ai_firewall.admission import Admission
from ai_firewall.ingress import ProtectedIngress


def client(inspector=None):
    app = FastAPI()
    writes = []

    @app.post('/api/v1/chats/new')
    async def save(request: Request):
        writes.append(await request.json())
        return {"saved": True}

    return TestClient(ProtectedIngress(app, inspector)), writes


def test_default_locked():
    api, writes = client()
    assert api.post('/api/v1/chats/new', json={"chat": {"title": "synthetic"}}).status_code == 403
    assert api.get('/health').json()['production_ready'] is False
    assert not writes


@pytest.mark.parametrize('path', ['/api/v1/chats/import', '/api/v1/files/',
    '/api/v1/retrieval/process/text', '/api/chat/completions', '/socket.io/',
    '/api/v1/chats/new/', '/api/v1/chats/new?bypass=1'])
def test_unsupported_direct_api(path):
    async def allow(*args):
        return True
    api, writes = client(allow)
    assert api.post(path, json={"chat": {"title": "synthetic"}}).status_code == 403
    assert not writes


def test_scan_precedes_write_and_canary_never_reaches_storage(caplog):
    canary = 'SYNTHETIC_SECRET_CANARY_6be42'
    async def inspect(body, scope):
        assert not writes
        return canary.encode() not in body
    api, writes = client(inspect)
    assert api.post('/api/v1/chats/new', json={"chat": {"title": canary}}).status_code == 403
    assert not writes
    assert canary not in caplog.text
    assert api.post('/api/v1/chats/new', json={"chat": {"title": "public"}}).status_code == 200
    assert writes == [{"chat": {"title": "public"}}]


def test_detector_failure_closed(caplog):
    async def broken(*args):
        raise RuntimeError('SYNTHETIC_SECRET_ERROR')
    api, writes = client(broken)
    assert api.post('/api/v1/chats/new', json={"chat": {"title": "test"}}).status_code == 503
    assert not writes
    assert 'SYNTHETIC_SECRET_ERROR' not in caplog.text


@pytest.mark.parametrize('body,status', [(b'{', 503), (b'x' * 20000, 413),
    (b'{"chat":{"title":"safe","files":[]}}', 403), (b'[]', 403)])
def test_malformed_and_unsupported(body, status):
    async def allow(*args):
        return True
    api, writes = client(allow)
    assert api.post('/api/v1/chats/new', content=body).status_code == status
    assert not writes


def test_receipt_scope_tampering_expiry_policy():
    now = [1000]
    key = secrets.token_bytes(32)
    admission = Admission(key, 'v1', lambda: now[0])
    token = admission.issue(b'sanitized', 'alice', 'create')
    assert admission.verify(token, b'sanitized', 'alice', 'create')
    for content, user, operation in [(b'raw', 'alice', 'create'),
            (b'sanitized', 'bob', 'create'), (b'sanitized', 'alice', 'edit')]:
        assert not admission.verify(token, content, user, operation)
    assert not admission.verify(token + '0', b'sanitized', 'alice', 'create')
    assert not Admission(key, 'v2', lambda: now[0]).verify(token, b'sanitized', 'alice', 'create')
    now[0] = 1030
    assert not admission.verify(token, b'sanitized', 'alice', 'create')


def test_websocket_denied():
    from starlette.websockets import WebSocketDisconnect
    api, writes = client()
    with pytest.raises(WebSocketDisconnect):
        with api.websocket_connect('/ws'):
            pass
    assert not writes