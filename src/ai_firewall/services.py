"""Synthetic-only POC services. No payload logging; authenticated internal APIs."""
import asyncio
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from ai_firewall.admission import Admission


def key(name):
    value = os.environ[name]
    if len(value) < 32:
        raise RuntimeError("key too short")
    return value


def auth(request, name):
    if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + key(name)):
        raise HTTPException(403, 'denied')


async def call(url, data, secret, method='POST'):
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.request(method, url, json=data if method == 'POST' else None,
                                            headers={'Authorization': 'Bearer ' + key(secret)})
        if response.status_code >= 400:
            raise HTTPException(502, 'dependency_denied')
        return response.json()
    except httpx.HTTPError:
        raise HTTPException(503, 'dependency_unavailable') from None


def database(path, schema):
    db = sqlite3.connect(path)
    db.execute(schema)
    db.commit()
    return db


def mock_app():
    app = FastAPI()
    state = {'scenario': os.getenv('MOCK_SCENARIO', 'echo'), 'last': None}
    scenarios = {'normal', 'echo', 'template', 'leak', 'injection', 'error', 'timeout'}

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.get('/v1/models')
    async def models(request: Request):
        auth(request, 'MOCK_KEY')
        return {'object': 'list', 'data': [{'id': 'mock', 'object': 'model', 'created': 0, 'owned_by': 'poc'}]}

    @app.post('/test/scenario')
    async def scenario(request: Request):
        auth(request, 'TEST_KEY')
        data = await request.json()
        if data.get('scenario') not in scenarios:
            raise HTTPException(400, 'unknown scenario')
        state['scenario'] = data['scenario']
        return {'ok': True}

    @app.get('/test/last')
    async def last(request: Request):
        auth(request, 'TEST_KEY')
        return {'messages': state['last']}

    @app.post('/v1/chat/completions')
    async def completion(request: Request):
        auth(request, 'MOCK_KEY')
        data = await request.json()
        if data.get('stream', False) is not False or set(data) - {'model', 'messages', 'stream', 'temperature', 'max_tokens', 'user'}:
            raise HTTPException(400, 'only non-stream text supported')
        messages = data.get('messages')
        if not isinstance(messages, list) or not messages or any(
            not isinstance(m, dict) or m.get('role') not in {'user', 'assistant', 'system'}
            or not isinstance(m.get('content'), str) or set(m) != {'role', 'content'} for m in messages
        ):
            raise HTTPException(400, 'invalid messages')
        state['last'] = messages
        mode = state['scenario']
        if mode == 'error':
            raise HTTPException(500, 'synthetic failure')
        if mode == 'timeout':
            await asyncio.sleep(15)
        text = {'normal': 'Synthetic response.', 'template': 'Synthetic template: approved.',
                'leak': 'SYNTHETIC_PII_OUTPUT_CANARY',
                'injection': 'SYNTHETIC_BLOCK_IGNORE_POLICY'}.get(mode, messages[-1]['content'])
        return {'id': 'chatcmpl-mock', 'object': 'chat.completion', 'created': 0, 'model': 'mock',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}
    return app


def vault_app():
    app = FastAPI()
    db = database('/data/vault.db', 'CREATE TABLE IF NOT EXISTS entries(token TEXT PRIMARY KEY, user TEXT, chat TEXT, value TEXT, expires REAL)')

    @app.post('/store')
    async def store(request: Request):
        auth(request, 'VAULT_KEY')
        data = await request.json()
        if not data['value'].startswith('SYNTHETIC_PII_'):
            raise HTTPException(403, 'synthetic only')
        token = '[PII_' + secrets.token_hex(24) + ']'
        with db:
            db.execute('DELETE FROM entries WHERE expires <= ?', (time.time(),))
            db.execute('INSERT INTO entries VALUES(?,?,?,?,?)',
                       (token, data['user'], data['chat'], data['value'], time.time() + int(os.getenv('VAULT_TTL', '3600'))))
        return {'token': token}

    @app.post('/reveal')
    async def reveal(request: Request):
        auth(request, 'VAULT_KEY')
        data = await request.json()
        text = data['text']
        for token in set(re.findall(r'\[PII_[a-f0-9]{48}\]', text)):
            row = db.execute('SELECT value FROM entries WHERE token=? AND user=? AND chat=? AND expires>?',
                             (token, data['user'], data['chat'], time.time())).fetchone()
            if row:
                text = text.replace(token, row[0])
        return {'text': text}
    return app


class SyntheticDetector:
    """Mandatory detector interface; replace/extend with NER adapters before real data."""
    def inspect(self, text):
        if os.getenv('DETECTOR_FAILURE') == '1':
            raise RuntimeError('mandatory detector unavailable')
        return list(re.finditer(r'SYNTHETIC_PII_[A-Za-z0-9_]+', text))


def gateway_app():
    app = FastAPI()
    detector = SyntheticDetector()
    admission = Admission(key('ADMISSION_KEY').encode(), 'synthetic-v2')

    async def scan(text, user, chat):
        try:
            matches = detector.inspect(text)
        except Exception:
            raise HTTPException(503, 'mandatory_detector_failed') from None
        if 'SYNTHETIC_BLOCK_' in text:
            raise HTTPException(403, 'BLOCK')
        for match in reversed(matches):
            item = await call('http://vault:8000/store', {'value': match.group(), 'user': user, 'chat': chat}, 'VAULT_KEY')
            text = text[:match.start()] + item['token'] + text[match.end():]
        return text, 'MASK' if matches else 'ALLOW'

    @app.get('/')
    async def ui():
        return HTMLResponse('''<!doctype html><meta charset="utf-8"><h1>AI Firewall synthetic POC</h1>
<p>Only synthetic data. Token stays in memory; no browser storage.</p>
<input id="key" type="password" placeholder="User API key"><textarea id="text"></textarea>
<button id="send">Send</button><button id="view">Reveal last response</button><pre id="out"></pre>
<script>let chat;const out=document.querySelector('#out');async function req(path,body){const r=await fetch(path,{method:'POST',headers:{'Authorization':'Bearer '+document.querySelector('#key').value,'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();out.textContent=JSON.stringify(d,null,2);return d;}document.querySelector('#send').onclick=async()=>{const d=await req('/chat',{text:document.querySelector('#text').value});chat=d.chat_id;document.querySelector('#text').value='';};document.querySelector('#view').onclick=()=>req('/view',{chat_id:chat});</script>''', headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "default-src 'self'; script-src 'unsafe-inline'; connect-src 'self'"})

    def user(request):
        auth(request, 'USER_KEY')
        return 'synthetic-user'

    @app.post('/check')
    async def check(request: Request):
        uid = user(request)
        data = await request.json()
        if set(data) != {'text'} or not isinstance(data['text'], str) or len(data['text']) > 8000:
            raise HTTPException(400, 'invalid schema')
        text, action = await scan(data['text'], uid, str(uuid.uuid4()))
        return {'text': text, 'action': action}

    @app.post('/chat')
    async def chat(request: Request):
        uid = user(request)
        data = await request.json()
        if set(data) != {'text'} or not isinstance(data['text'], str) or len(data['text']) > 8000:
            raise HTTPException(400, 'invalid schema')
        cid = str(uuid.uuid4())
        text, action = await scan(data['text'], uid, cid)
        result = await call('http://litellm:4000/v1/chat/completions',
                            {'model': 'mock', 'stream': False, 'messages': [{'role': 'user', 'content': text}]}, 'LITELLM_KEY')
        output, _ = await scan(result['choices'][0]['message']['content'], uid, cid)
        payload = {'id': cid, 'user': uid, 'input': text, 'output': output}
        body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        token = admission.issue(body, uid, 'create')
        await call('http://webui:8080/firewall/save', {'payload': payload, 'admission': token}, 'STORE_KEY')
        return {'chat_id': cid, 'action': action, 'input': text, 'output': output}

    @app.post('/view')
    async def view(request: Request):
        uid = user(request)
        data = await request.json()
        if set(data) != {'chat_id'}:
            raise HTTPException(400, 'invalid schema')
        stored = await call('http://webui:8080/firewall/read', {'id': data['chat_id'], 'user': uid}, 'STORE_KEY')
        result = await call('http://vault:8000/reveal', {'user': uid, 'chat': data['chat_id'], 'text': stored['output']}, 'VAULT_KEY')
        from fastapi.responses import JSONResponse
        return JSONResponse(result, headers={'Cache-Control': 'no-store'})
    return app


app = ({'mock': mock_app, 'vault': vault_app, 'gateway': gateway_app}[os.environ['SERVICE']]()
       if os.getenv('SERVICE') in {'mock', 'vault', 'gateway'} else None)