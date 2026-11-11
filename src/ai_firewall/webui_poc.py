"""Outer fail-closed adapter. Only inspected, one-use receipts reach real Chats."""
import json
import sqlite3
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from ai_firewall.admission import Admission
from ai_firewall.ingress import ProtectedIngress
from ai_firewall.services import auth, key


def protect(upstream):
    api = FastAPI()
    admission = Admission(key('ADMISSION_KEY').encode(), 'synthetic-v2')
    db = sqlite3.connect('/app/backend/data/admission.db')
    db.execute('CREATE TABLE IF NOT EXISTS consumed(token TEXT PRIMARY KEY, expires REAL)')

    @api.post('/firewall/save')
    async def save(request: Request):
        auth(request, 'STORE_KEY')
        from open_webui.models.chats import Chats, ChatForm
        from open_webui.models.users import Users
        data = await request.json()
        payload, token = data['payload'], data['admission']
        if set(payload) != {'id', 'user', 'input', 'output'} or payload['user'] != 'synthetic-user':
            raise HTTPException(403, 'scope denied')
        uuid.UUID(payload['id'])
        body = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
        if not admission.verify(token, body, payload['user'], 'create'):
            raise HTTPException(403, 'receipt denied')
        try:
            with db:
                db.execute('DELETE FROM consumed WHERE expires <= ?', (time.time(),))
                db.execute('INSERT INTO consumed VALUES(?,?)', (token, time.time() + 60))
        except sqlite3.IntegrityError:
            raise HTTPException(403, 'replay denied') from None
        if not await Users.get_user_by_id(payload['user']):
            await Users.insert_new_user(payload['user'], 'Synthetic POC', 'synthetic@example.invalid', role='admin')
        messages = [{'id': str(uuid.uuid4()), 'role': role, 'content': payload[field]}
                    for role, field in [('user', 'input'), ('assistant', 'output')]]
        saved = await Chats.insert_new_chat(payload['id'], payload['user'], ChatForm(chat={'title': 'Synthetic POC', 'messages': messages}))
        if not saved:
            raise HTTPException(503, 'save failed')
        return {'saved': True}

    @api.post('/firewall/read')
    async def read(request: Request):
        auth(request, 'STORE_KEY')
        from open_webui.models.chats import Chats
        data = await request.json()
        item = await Chats.get_chat_by_id_and_user_id(data['id'], data['user'])
        if not item:
            raise HTTPException(404, 'not found')
        return {'output': item.chat['messages'][-1]['content']}

    locked = ProtectedIngress(upstream)

    async def application(scope, receive, send):
        if scope['type'] == 'http' and scope['path'] in {'/firewall/save', '/firewall/read'} and scope['method'] == 'POST' and not scope.get('query_string'):
            body = bytearray()
            while True:
                event = await receive()
                if event['type'] == 'http.disconnect':
                    return
                body.extend(event.get('body', b''))
                if len(body) > 32768:
                    from starlette.responses import JSONResponse
                    return await JSONResponse({'detail': 'too large'}, status_code=413)(scope, receive, send)
                if not event.get('more_body'):
                    break
            async def replay():
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await api(scope, replay, send)
        return await locked(scope, receive, send)
    return application