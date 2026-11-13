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

from ai_firewall.admission import Admission
from ai_firewall.batch import inspect_batch, native_context
from ai_firewall.protocol import canonical, context, harden, identity, schema, text as validate_text, version


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
            if response.status_code == 403 and url.endswith('/inspect'):
                verdict = response.json().get('detail')
                if isinstance(verdict,dict) and verdict.get('action') in {'BLOCK','REVIEW'}:
                    raise HTTPException(403,verdict)
                if isinstance(verdict,str) and verdict in {'BLOCK', 'REVIEW'}: raise HTTPException(403, verdict)
            status = response.status_code if response.status_code in {403, 404, 409} else 502
            raise HTTPException(status, 'dependency_denied')
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
    if os.getenv('DLP_DEBUG_TEST_ONLY') == 'true': scenarios.add('dlp-debug')

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

    @app.get('/test/scenario')
    async def get_scenario(request: Request):
        auth(request, 'TEST_KEY')
        return {'scenario': state['scenario']}

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
        schema(data, {'value', 'user', 'chat'})
        if not isinstance(data['value'], str) or not re.fullmatch(r'SYNTHETIC_PII_[A-Za-z0-9_]{1,7900}', data['value']):
            raise HTTPException(403, 'synthetic only')
        if data['user'] in {'synthetic-user', 'synthetic-bob'}:
            context(data['user'], data['chat'])
        else:
            native_context(data['user'], data['chat'])
        row = db.execute('SELECT token FROM entries WHERE user=? AND chat=? AND value=? AND expires>?',
                         (data['user'], data['chat'], data['value'], time.time())).fetchone()
        if row:
            with db:
                db.execute('UPDATE entries SET expires=? WHERE token=?',
                           (time.time() + int(os.getenv('VAULT_TTL', '3600')), row[0]))
            return {'token': row[0]}
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
        schema(data, {'text', 'user', 'chat'})
        if not isinstance(data['text'], str) or len(data['text']) > 8000:
            raise HTTPException(400, 'invalid_text')
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

    @app.post('/native/review-model')
    async def review_model(request: Request):
        auth(request,'NATIVE_GATEWAY_KEY')
        from ai_firewall.review_contract import scope,verify
        data=await request.json()
        schema(data,{'event','fields','user','chat','policy','permit'})
        native_context(data['user'],data['chat'])
        if set(data['fields'])!={'content'}:raise HTTPException(400,'review_fields_invalid')
        raw=validate_text(data['fields']['content'])
        claims=scope(data['event'],data['fields'],data['user'],data['chat'],data['policy'])
        nonce=verify(key('ADMISSION_KEY'),data['permit'],claims)
        # Re-run mandatory detectors and active policy; only a current REVIEW qualifies.
        detector.inspect(raw)
        async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
            headers={'Authorization':'Bearer '+key('NATIVE_GATEWAY_KEY')}
            active=await client.post(os.environ['PII_TEST_URL']+'/policy-manager',headers=headers,
                json={'action':'view','actor':data['user']})
            if active.status_code!=200 or active.json()['active']!=data['policy']:
                raise HTTPException(409,'review_policy_changed')
            response=await client.post(os.environ['PII_TEST_URL']+'/inspect',headers=headers,
                json={'fields':data['fields'],'operation':'model-request','user':data['user'],'chat':data['chat'],'policy_revision':data['policy']})
        detail=response.json().get('detail',{})
        if response.status_code!=403 or not isinstance(detail,dict) or detail.get('action')!='REVIEW':
            raise HTTPException(403,'review_no_longer_eligible')
        # Shared persistent replay store. Claim before returning any model content.
        db=sqlite3.connect(os.getenv('REVIEW_NONCE_DB','/tmp/review-nonces.db'),timeout=15)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS used_review(nonce TEXT PRIMARY KEY)')
                db.execute('INSERT INTO used_review VALUES(?)',(nonce,))
        except sqlite3.IntegrityError:raise HTTPException(409,'review_permit_replayed') from None
        finally:db.close()
        return {'fields':data['fields'],'policy_revision':data['policy']}

    @app.post('/native/delta-permit')
    async def delta_permit(request:Request):
        auth(request,'NATIVE_GATEWAY_KEY')
        data=await request.json();schema(data,{'payload','delta'})
        payload=data['payload']
        schema(payload,{'fields','before','delta','user','chat','operation','revision'})
        if payload['operation']!='chat-delta':raise HTTPException(400,'delta_operation_invalid')
        if json.dumps(payload['delta'],sort_keys=True,separators=(',',':'))!=data['delta']:raise HTTPException(400,'delta_mismatch')
        class Inspection:
            headers=request.headers
            async def json(self):return dict(fields={'delta':data['delta']},user=payload['user'],chat=payload['chat'],operation='chat-write',revision=payload['revision'])
        checked=await native_inspect(Inspection())
        if checked['action']!='ALLOW' or checked['payload']['fields']!={'delta':data['delta']}:
            raise HTTPException(403,'delta_not_canonical')
        return {'payload':payload,'action':'ALLOW','admission':admission.issue(canonical(payload),payload['user'],'chat-delta')}

    @app.post('/native/delete-permit')
    async def delete_permit(request: Request):
        auth(request,'NATIVE_GATEWAY_KEY')
        from ai_firewall.delete_contract import validate_delete
        try:
            data=validate_delete(await request.json())
        except HTTPException: raise
        except Exception: raise HTTPException(400,'invalid_delete_manifest') from None
        return {'payload':data,'admission':admission.issue(canonical(data),data['user'],'chat-delete')}

    @app.post('/native/inspect')
    async def native_inspect(request: Request):
        auth(request, 'NATIVE_GATEWAY_KEY')

        async def store(value, user, chat):
            result = await call('http://vault:8000/store',
                                {'value': value, 'user': user, 'chat': chat}, 'VAULT_KEY')
            return result['token']

        data = await request.json()
        # Final synthetic batch policies precede encrypted and legacy storage.
        if any('SYNTHETIC_BLOCK_' in v for v in data.get('fields', {}).values() if isinstance(v, str)):
            raise HTTPException(403, 'BLOCK')
        if any('SYNTHETIC_REVIEW_' in v for v in data.get('fields', {}).values() if isinstance(v, str)):
            raise HTTPException(403, 'REVIEW')
        nlp = None
        if os.getenv('PII_TEST_URL'):
            # Mandatory bounded worker; no Vault call until its full verdict.
            nlp = await call(os.environ['PII_TEST_URL'] + '/inspect',
                {'fields': data.get('fields'), 'operation': data.get('operation'),
                 'user':data.get('user'),'chat':data.get('chat'),
                 'policy_revision':request.headers.get('X-Policy-Revision') or None}, 'NATIVE_GATEWAY_KEY')
            if (nlp.get('action') not in {'ALLOW', 'MASK'} or not isinstance(nlp.get('fields'), dict)
                    or set(nlp['fields']) != set(data.get('fields', {}))):
                raise HTTPException(503, 'invalid_nlp_verdict')
            if os.getenv('VAULT_V2_URL') and nlp['action'] == 'MASK':
                from pathlib import Path
                raw = data['fields']
                spans = [(name, span) for name in sorted(raw) for span in nlp['spans'][name]]
                if not 1<=len(spans)<=128: raise HTTPException(503,'invalid_mask_spans')
                for name in raw:
                    end=0
                    for s in nlp['spans'][name]:
                        if (set(s)!={'start','end'} or type(s['start']) is not int or type(s['end']) is not int
                                or not end<=s['start']<s['end']<=len(raw[name])):
                            raise HTTPException(503,'invalid_mask_spans')
                        end=s['end']
                try:
                    async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
                        response = await client.post(os.environ['VAULT_V2_URL'] + '/store-batch',
                            headers={'Authorization': 'Bearer ' + Path(os.environ['VAULT_V2_WRITE_KEY_FILE']).read_text().strip()},
                            json={'tenant': 'synthetic', 'user': data['user'], 'chat': data['chat'],
                                  'values': [raw[name][s['start']:s['end']] for name,s in spans],
                                  'verdict': 'MASK', 'policy_version': nlp['policy_version'],
                                  'policy_revision':nlp['policy_revision'],'mask_approval':nlp.get('mask_approval')})
                        response.raise_for_status()
                        tokens = response.json()['tokens']
                    cleaned = dict(raw)
                    for (name,s), token in reversed(list(zip(spans,tokens,strict=True))):
                        if not re.fullmatch(r'\[V2_[a-f0-9]{64}\]', token): raise ValueError()
                        cleaned[name] = cleaned[name][:s['start']] + token + cleaned[name][s['end']:]
                    nlp['fields'] = cleaned
                except Exception:
                    raise HTTPException(503, 'encrypted_vault_unavailable') from None
            data = {**data, 'fields': nlp['fields']}
        result = await inspect_batch(data, detector, store, admission)
        if nlp and nlp['action'] == 'MASK': result['action'] = 'MASK'
        result['categories'] = sorted(set((nlp['categories'] if nlp else []) +
            (['SYNTHETIC_PII'] if result['action'] == 'MASK' and not (nlp and nlp['categories']) else [])))
        result['policy_version'] = nlp['policy_version'] if nlp else 'synthetic-v2'
        result['policy_revision'] = nlp.get('policy_revision') if nlp else None
        result['findings'] = nlp.get('findings',[]) if nlp else []
        return result

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

    @app.post('/check')
    async def check(request: Request):
        uid = identity(request)
        data = await request.json()
        schema(data, {'text'})
        value, action = await scan(validate_text(data['text']), uid, str(uuid.uuid4()))
        return {'text': value, 'action': action}

    @app.post('/chat')
    async def chat(request: Request):
        uid = identity(request)
        data = await request.json()
        schema(data, {'text'}, {'chat_id'})
        raw = validate_text(data['text'])
        cid = data.get('chat_id') or str(uuid.uuid4())
        context(uid, cid)
        # Read ownership and history from storage, never accept client history.
        previous = []
        exists = bool(data.get('chat_id'))
        if exists:
            stored = await call('http://webui:8080/firewall/read', {'id': cid, 'user': uid}, 'STORE_KEY')
            previous = stored['messages']
        if len(previous) >= 40:
            raise HTTPException(409, 'turn_limit')
        cleaned, action = await scan(raw, uid, cid)
        inference = [{'role': m['role'], 'content': m['content']} for m in previous]
        # Mandatory detectors must remain available for every inference context.
        # A pre-existing row containing a raw synthetic marker is never forwarded.
        try:
            for message in inference:
                if detector.inspect(message['content']) or 'SYNTHETIC_BLOCK_' in message['content']:
                    raise ValueError('unsafe stored history')
        except Exception:
            raise HTTPException(503, 'stored_history_check_failed') from None
        inference.append({'role': 'user', 'content': cleaned})
        result = await call('http://litellm:4000/v1/chat/completions',
                            {'model': 'mock', 'stream': False, 'messages': inference}, 'LITELLM_KEY')
        output, _ = await scan(validate_text(result['choices'][0]['message']['content']), uid, cid)
        payload = {'id': cid, 'user': uid, 'input': cleaned, 'output': output,
                   'base': version(previous), 'exists': exists}
        operation = 'append' if exists else 'create'
        token = admission.issue(canonical(payload), uid, operation)
        await call('http://webui:8080/firewall/save', {'payload': payload, 'admission': token}, 'STORE_KEY')
        return {'chat_id': cid, 'action': action, 'input': cleaned, 'output': output}

    @app.post('/history')
    async def history(request: Request):
        uid = identity(request)
        data = await request.json()
        schema(data, {'chat_id'})
        context(uid, data['chat_id'])
        return await call('http://webui:8080/firewall/read', {'id': data['chat_id'], 'user': uid}, 'STORE_KEY')

    @app.post('/chats')
    async def chats(request: Request):
        uid = identity(request)
        schema(await request.json(), set())
        return await call('http://webui:8080/firewall/list', {'user': uid}, 'STORE_KEY')

    @app.post('/view')
    async def view(request: Request):
        uid = identity(request)
        data = await request.json()
        schema(data, {'chat_id'}, {'message_id'})
        context(uid, data['chat_id'])
        stored = await call('http://webui:8080/firewall/read', {'id': data['chat_id'], 'user': uid}, 'STORE_KEY')
        message = next((m for m in stored['messages'] if m['id'] == data.get('message_id')), None)
        if data.get('message_id') and message is None:
            raise HTTPException(404, 'not_found')
        value = message['content'] if message else stored['output']
        return await call('http://vault:8000/reveal', {'user': uid, 'chat': data['chat_id'], 'text': value}, 'VAULT_KEY')

    return app


app = ({'mock': mock_app, 'vault': vault_app, 'gateway': gateway_app}[os.environ['SERVICE']]()
       if os.getenv('SERVICE') in {'mock', 'vault', 'gateway'} else None)
if app is not None:
    app = harden(app)
