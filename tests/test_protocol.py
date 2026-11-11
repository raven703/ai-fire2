import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from ai_firewall.protocol import context, harden, schema, text


def test_strict_schema_context_and_content():
    for data in [[], None, {'text': 'safe', 'history': []}]:
        with pytest.raises(HTTPException):
            schema(data, {'text'})
    for value in ['', '\x00', 'x' * 8001, [], None]:
        with pytest.raises(HTTPException):
            text(value)
    with pytest.raises(HTTPException):
        context('outsider', 'a')


def test_processing_errors_have_no_payload_and_no_exception_log(caplog):
    app = FastAPI()

    @app.post('/broken')
    async def broken():
        raise RuntimeError('SYNTHETIC_PII_EXCEPTION_CANARY')

    api = TestClient(harden(app))
    response = api.post('/broken')
    assert response.status_code == 503
    assert 'SYNTHETIC_PII_' not in response.text + caplog.text
    assert response.headers['cache-control'] == 'no-store'


def test_body_is_bounded_before_handler():
    app = FastAPI()
    api = TestClient(harden(app))
    assert api.post('/anything', content=b'x' * 262145).status_code == 413