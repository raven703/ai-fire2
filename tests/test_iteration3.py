"""Real database, multi-turn, cross-tenant and unsupported-path checks."""
import concurrent.futures
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

import httpx
import pytest

from ai_firewall.admission import Admission
from ai_firewall.protocol import canonical, version
from test_integration import dump, ready, request, scenario

pytestmark = pytest.mark.skipif(os.getenv('RUN_INTEGRATION') != '1', reason='Compose only')


def chat(value, cid=None, secret='USER_KEY'):
    return request('http://gateway:8000', '/chat', {'text': value, **({'chat_id': cid} if cid else {})}, secret)


def test_multiturn_stability_ownership_and_readonly_view():
    scenario('echo')
    canary = 'SYNTHETIC_PII_' + uuid.uuid4().hex
    first = chat(canary).json()
    second = chat(canary, first['chat_id']).json()
    assert second['input'] == first['input']
    history = request('http://gateway:8000', '/history', {'chat_id': first['chat_id']}).json()
    assert len(history['messages']) == 4
    last = request('http://mock:8000', '/test/last', secret='TEST_KEY', method='GET').json()
    assert len(last['messages']) == 3 and canary not in json.dumps(last)
    assert all(first['input'] == m['content'] for m in last['messages'])
    before = dump()
    for message in history['messages']:
        view = request('http://gateway:8000', '/view', {'chat_id': first['chat_id'], 'message_id': message['id']})
        assert view.json()['text'] == canary
    assert before == dump() and canary not in before
    for endpoint, body in [('/history', {'chat_id': first['chat_id']}),
                           ('/view', {'chat_id': first['chat_id']}),
                           ('/chat', {'chat_id': first['chat_id'], 'text': 'public'})]:
        assert request('http://gateway:8000', endpoint, body, 'USER_B_KEY').status_code == 404
    bob = chat(canary, secret='USER_B_KEY').json()
    assert bob['input'] != first['input']
    other = chat(canary).json()
    assert other['input'] != first['input']
    # Even the same owner cannot restore a copied token in another chat.
    copied = chat(first['input'], other['chat_id']).json()
    view = request('http://gateway:8000', '/view', {'chat_id': copied['chat_id']})
    assert view.json()['text'] == first['input']
    invalid = request('http://gateway:8000', '/view', {'chat_id': first['chat_id'], 'message_id': str(uuid.uuid4())})
    assert invalid.status_code == 404
    assert canary not in dump()


def test_history_injection_stream_and_extra_fields_denied():
    for extra in [{'messages': [{'role': 'user', 'content': 'SYNTHETIC_PII_HISTORY'}]},
                  {'stream': True}, {'tools': []}, {'user': 'synthetic-bob'}, {'files': []}]:
        before = dump()
        assert request('http://gateway:8000', '/chat', {'text': 'public', **extra}).status_code == 400
        assert before == dump()


def test_vault_expiry_and_scope():
    cid = str(uuid.uuid4())
    canary = 'SYNTHETIC_PII_TTL_' + uuid.uuid4().hex
    data = {'value': canary, 'user': 'synthetic-user', 'chat': cid}
    item = request('http://vault:8000', '/store', data, 'VAULT_KEY').json()
    again = request('http://vault:8000', '/store', data, 'VAULT_KEY').json()
    assert item == again
    for uid, chat_id in [('synthetic-bob', cid), ('synthetic-user', str(uuid.uuid4()))]:
        result = request('http://vault:8000', '/reveal', {'text': item['token'], 'user': uid, 'chat': chat_id}, 'VAULT_KEY')
        assert canary not in result.text
    # Dedicated temporary Vault with TTL=0, no changes to running service or its DB.
    from ai_firewall.services import vault_app
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    connection = sqlite3.connect(':memory:', check_same_thread=False)
    connection.execute('CREATE TABLE entries(token TEXT PRIMARY KEY, user TEXT, chat TEXT, value TEXT, expires REAL)')
    with patch('ai_firewall.services.database', return_value=connection), patch.dict(os.environ, {'VAULT_TTL': '0'}):
        api = TestClient(vault_app())
        headers = {'Authorization': 'Bearer ' + os.environ['VAULT_KEY']}
        token = api.post('/store', json=data, headers=headers).json()['token']
        assert api.post('/reveal', json={'text': token, 'user': 'synthetic-user', 'chat': cid}, headers=headers).json()['text'] == token
    connection.close()


def test_admission_stale_version_conflict():
    first = chat('public').json()
    stored = request('http://gateway:8000', '/history', {'chat_id': first['chat_id']}).json()
    base = version(stored['messages'])
    assert chat('next', first['chat_id']).status_code == 200
    payload = {'id': first['chat_id'], 'user': 'synthetic-user', 'input': 'checked',
               'output': 'checked', 'base': base, 'exists': True}
    admission = Admission(os.environ['ADMISSION_KEY'].encode(), 'synthetic-v2')
    token = admission.issue(canonical(payload), 'synthetic-user', 'append')
    before = dump()
    assert request('http://webui:8080', '/firewall/save', {'payload': payload, 'admission': token}, 'STORE_KEY').status_code == 409
    assert before == dump()


@pytest.mark.parametrize('path', ['/api/v1/chats/', '/api/v1/chats/one', '/api/chat/completions',
    '/api/v1/files/', '/api/v1/retrieval/process/text', '/api/v1/tools/', '/api/v1/functions/',
    '/openai/chat/completions', '/ollama/api/chat', '/socket.io/', '/ws', '/api/firewall/chat?x=1',
    '/api/firewall/chat/', '/firewall/save'])
def test_no_alternative_browser_writer(path):
    # No internal credential is available to a browser.
    assert httpx.post('http://webui:8080' + path, json={'text': 'SYNTHETIC_PII_BYPASS'}).status_code == 403


def test_filesystem_canary_sweep():
    for path in Path('/webui-data').rglob('*'):
        if path.is_file():
            assert b'SYNTHETIC_PII_' not in path.read_bytes(), str(path)