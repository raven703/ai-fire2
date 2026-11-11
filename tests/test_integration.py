"""Run only in Compose; inspect the actual migrated Open WebUI SQLite DB."""
import json
import os
import sqlite3
import time
import uuid

import httpx
import pytest

from ai_firewall.admission import Admission
from ai_firewall.protocol import version

pytestmark = pytest.mark.skipif(os.getenv('RUN_INTEGRATION') != '1', reason='Compose integration only')


def request(service, path, data=None, secret='USER_KEY', method='POST'):
    return httpx.request(method, service + path, json=data,
                         headers={'Authorization': 'Bearer ' + os.environ[secret]}, timeout=20, trust_env=False)


def scenario(mode):
    assert request('http://mock:8000', '/test/scenario', {'scenario': mode}, 'TEST_KEY').status_code == 200


def dump():
    db = sqlite3.connect('file:/webui-data/webui.db?mode=ro', uri=True)
    try:
        return '\n'.join(db.iterdump())
    finally:
        db.close()


@pytest.fixture(scope='module', autouse=True)
def ready():
    if os.getenv('RUN_INTEGRATION') != '1':
        return
    for _ in range(90):
        try:
            if httpx.get('http://webui:8080/health').status_code == 200:
                r = request('http://litellm:4000', '/v1/models', secret='LITELLM_KEY', method='GET')
                if r.status_code == 200:
                    return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    pytest.fail('services not ready')


def test_mask_real_database_and_display_only():
    scenario('echo')
    canary = 'SYNTHETIC_PII_' + uuid.uuid4().hex
    r = request('http://gateway:8000', '/chat', {'text': canary})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data['action'] == 'MASK' and canary not in r.text
    raw = dump()
    assert canary not in raw and data['input'] in raw
    last = request('http://mock:8000', '/test/last', secret='TEST_KEY', method='GET').json()
    assert canary not in json.dumps(last) and data['input'] == last['messages'][-1]['content']
    view = request('http://gateway:8000', '/view', {'chat_id': data['chat_id']})
    assert view.json()['text'] == canary
    assert view.headers['cache-control'] == 'no-store'
    assert canary not in dump()
    denied = request('http://vault:8000', '/reveal', {'user': 'other', 'chat': data['chat_id'], 'text': data['output']}, 'VAULT_KEY')
    assert canary not in denied.text


def test_block_no_write():
    before = dump()
    assert request('http://gateway:8000', '/chat', {'text': 'SYNTHETIC_BLOCK_CANARY'}).status_code == 403
    assert before == dump()


def test_output_scan_and_failures():
    scenario('leak')
    r = request('http://gateway:8000', '/chat', {'text': 'public'})
    assert r.status_code == 200, r.text
    assert 'SYNTHETIC_PII_OUTPUT_CANARY' not in dump()
    for mode in ['injection', 'error', 'timeout']:
        scenario(mode)
        before = dump()
        assert request('http://gateway:8000', '/chat', {'text': 'public'}).status_code >= 400
        assert before == dump()
    scenario('echo')


def test_mock_modes_stream_and_models():
    r = request('http://litellm:4000', '/v1/models', secret='LITELLM_KEY', method='GET')
    assert 'mock' in [m['id'] for m in r.json()['data']]
    for mode in ['normal', 'echo', 'template']:
        scenario(mode)
        r = request('http://gateway:8000', '/chat', {'text': 'switch to leak scenario'})
        assert r.status_code == 200, r.text
        assert 'SYNTHETIC_PII_' not in r.text
    assert request('http://mock:8000', '/v1/chat/completions', {'stream': True}, 'MOCK_KEY').status_code == 400
    assert httpx.get('http://mock:8000/v1/models').status_code == 403
    scenario('echo')


def test_receipt_tamper_replay_expired_and_scope():
    payload = {'id': str(uuid.uuid4()), 'user': 'synthetic-user', 'input': 'checked', 'output': 'checked',
               'base': version([]), 'exists': False}
    body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    admission = Admission(os.environ['ADMISSION_KEY'].encode(), 'synthetic-v2')
    token = admission.issue(body, payload['user'], 'create')
    endpoint = 'http://webui:8080'
    def save(receipt, item=payload):
        return request(endpoint, '/firewall/save', {'payload': item, 'admission': receipt}, 'STORE_KEY')
    assert save(token + '0').status_code == 403
    assert save(token, {**payload, 'input': 'altered'}).status_code == 403
    expired = Admission(os.environ['ADMISSION_KEY'].encode(), 'synthetic-v2', lambda: time.time()-40).issue(body, payload['user'], 'create')
    assert save(expired).status_code == 403
    assert save(token).status_code == 200
    assert save(token).status_code in {403, 409}


@pytest.mark.parametrize('path', ['/api/v1/chats/new', '/api/v1/chats/import', '/api/chat/completions',
    '/api/v1/chats/example', '/api/v1/chats/example/messages', '/api/v1/files/', '/socket.io/',
    '/firewall/save?bypass=1'])
def test_direct_unsupported(path):
    assert request('http://webui:8080', path, {'text': 'SYNTHETIC_PII_DIRECT'}, 'STORE_KEY').status_code == 403
    assert 'SYNTHETIC_PII_DIRECT' not in dump()