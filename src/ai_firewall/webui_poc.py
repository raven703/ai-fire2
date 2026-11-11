"""Fail-closed Open WebUI adapter: Svelte assets, sessions, inspected CAS writes."""
import asyncio
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ai_firewall.admission import Admission
from ai_firewall.ingress import ProtectedIngress
from ai_firewall.protocol import USERS, canonical, context, harden, identity, schema, text, version
from ai_firewall.services import auth, key


def protect(upstream):
    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    admission = Admission(key('ADMISSION_KEY').encode(), 'synthetic-v2')
    db = sqlite3.connect('/app/backend/data/admission.db')
    db.execute('CREATE TABLE IF NOT EXISTS consumed(token TEXT PRIMARY KEY, expires REAL)')
    sessions = {}  # opaque session identifiers, RAM only, lost on restart
    writer_lock = asyncio.Lock()  # one uvicorn worker; CAS covers concurrent turns

    def session(request):
        value = sessions.get(request.cookies.get('firewall_session', ''))
        if not value or value['expires'] <= time.time():
            raise HTTPException(403, 'authentication_required')
        return value

    def same_origin(request):
        origin = request.headers.get('origin')
        if origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'origin_denied')

    @api.post('/api/firewall/login')
    async def login(request: Request):
        same_origin(request)
        data = await request.json()
        schema(data, {'key'})
        if not isinstance(data['key'], str):
            raise HTTPException(403, 'authentication_required')
        uid = next((u for u, name in USERS.items() if len(os.getenv(name, '')) >= 32 and
                    hmac.compare_digest(data['key'], os.environ[name])), None)
        if not uid:
            raise HTTPException(403, 'authentication_required')
        now = time.time()
        for token in list(sessions):
            if sessions[token]['expires'] <= now:
                del sessions[token]
        sid = secrets.token_urlsafe(32)
        sessions[sid] = {'user': uid, 'expires': now + 3600}
        response = JSONResponse({'user': uid})
        response.set_cookie('firewall_session', sid, httponly=True, samesite='strict', path='/')
        return response

    @api.get('/api/firewall/session')
    async def current(request: Request):
        return {'user': session(request)['user']}

    @api.post('/api/firewall/logout')
    async def logout(request: Request):
        same_origin(request)
        sessions.pop(request.cookies.get('firewall_session', ''), None)
        response = JSONResponse({'ok': True})
        response.delete_cookie('firewall_session')
        return response

    @api.post('/api/firewall/{operation}')
    async def browser(request: Request, operation: str):
        same_origin(request)
        uid = session(request)['user']
        if operation not in {'chat', 'chats', 'history', 'view'}:
            raise HTTPException(403, 'unsupported')
        # The only raw-body path is an in-memory proxy to mandatory inspection.
        try:
            async with httpx.AsyncClient(timeout=12, trust_env=False) as client:
                response = await client.post('http://gateway:8000/' + operation,
                                             content=await request.body(), headers={
                                                 'Authorization': 'Bearer ' + key(USERS[uid]),
                                                 'Content-Type': 'application/json'})
            if response.status_code >= 400:
                detail = 'BLOCK: запрос запрещён политикой.' if response.status_code == 403 else 'Проверка или сервис недоступны. Сообщение не сохранено.'
                return JSONResponse({'detail': detail}, status_code=response.status_code)
            return JSONResponse(response.json())
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, 'Privacy Gateway недоступен. Сообщение не сохранено.') from None

    async def owned(cid, uid):
        from open_webui.models.chats import Chats
        context(uid, cid)
        item = await Chats.get_chat_by_id_and_user_id(cid, uid)
        if not item:
            raise HTTPException(404, 'not_found')
        return item

    @api.post('/firewall/save')
    async def save(request: Request):
        auth(request, 'STORE_KEY')
        from open_webui.models.chats import Chats, ChatForm
        from open_webui.models.users import Users as WebUsers
        data = await request.json()
        schema(data, {'payload', 'admission'})
        payload, token = data['payload'], data['admission']
        schema(payload, {'id', 'user', 'input', 'output', 'base', 'exists'})
        context(payload['user'], payload['id'])
        text(payload['input']); text(payload['output'])
        if type(payload['exists']) is not bool or not isinstance(token, str):
            raise HTTPException(403, 'receipt_denied')
        operation = 'append' if payload['exists'] else 'create'
        if not admission.verify(token, canonical(payload), payload['user'], operation):
            raise HTTPException(403, 'receipt_denied')
        async with writer_lock:
            if db.execute('SELECT 1 FROM consumed WHERE token=?', (token,)).fetchone():
                raise HTTPException(403, 'replay_denied')
            item = await Chats.get_chat_by_id(payload['id'])
            if item and item.user_id != payload['user']:
                raise HTTPException(403, 'scope_denied')
            previous = item.chat.get('messages', []) if item else []
            if bool(item) != payload['exists'] or version(previous) != payload['base'] or len(previous) >= 40:
                raise HTTPException(409, 'stale_history')
            try:
                with db:
                    db.execute('DELETE FROM consumed WHERE expires <= ?', (time.time(),))
                    db.execute('INSERT INTO consumed VALUES(?,?)', (token, time.time() + 60))
            except sqlite3.IntegrityError:
                raise HTTPException(403, 'replay_denied') from None
            if not await WebUsers.get_user_by_id(payload['user']):
                await WebUsers.insert_new_user(payload['user'], 'Synthetic POC', payload['user']+'@example.invalid', role='admin')
            messages = previous + [{'id': str(uuid.uuid4()), 'role': role, 'content': payload[field], 'done': True}
                                   for role, field in [('user', 'input'), ('assistant', 'output')]]
            history = {'messages': {}, 'currentId': messages[-1]['id']}
            for index, message in enumerate(messages):
                history['messages'][message['id']] = {**message,
                    'parentId': messages[index-1]['id'] if index else None,
                    'childrenIds': [messages[index+1]['id']] if index+1 < len(messages) else []}
            chat = {'title': 'Synthetic POC', 'models': ['mock'], 'messages': messages, 'history': history}
            saved = (await Chats.update_chat_by_id(payload['id'], chat) if item else
                     await Chats.insert_new_chat(payload['id'], payload['user'], ChatForm(chat=chat)))
            if not saved:
                raise HTTPException(503, 'save_failed')
        return {'saved': True}

    @api.post('/firewall/read')
    async def read(request: Request):
        auth(request, 'STORE_KEY')
        data = await request.json()
        schema(data, {'id', 'user'})
        item = await owned(data['id'], data['user'])
        messages = item.chat['messages']
        return {'id': item.id, 'messages': messages, 'output': messages[-1]['content']}

    @api.post('/firewall/list')
    async def listing(request: Request):
        auth(request, 'STORE_KEY')
        from open_webui.models.chats import Chats
        data = await request.json()
        schema(data, {'user'})
        if data['user'] not in USERS:
            raise HTTPException(403, 'scope_denied')
        items = await Chats.get_chat_list_by_user_id(data['user'], limit=50)
        return {'chats': [{'id': c.id, 'title': c.title} for c in items]}

    @api.get('/{path:path}')
    async def assets(path: str):
        build = Path('/app/build').resolve()
        # No arbitrary upstream static handlers, SPA fallback, source maps or APIs.
        if path == '' or re.fullmatch(r'c/[a-f0-9-]{36}', path):
            return FileResponse(build / 'index.html')
        if path.startswith('_app/') and path.endswith(('.js', '.css', '.woff2', '.png', '.json')):
            candidate = (build / path).resolve()
            if candidate.is_relative_to(build) and candidate.is_file():
                return FileResponse(candidate)
        if path in {'static/favicon.png', 'static/favicon-96x96.png', 'static/favicon.svg',
                    'static/favicon.ico', 'static/apple-touch-icon.png',
                    'static/splash.png', 'static/splash-dark.png', 'manifest.json'}:
            return FileResponse(build / path)
        raise HTTPException(403, 'unsupported')

    locked = ProtectedIngress(upstream)
    protected_api = harden(api)

    async def application(scope, receive, send):
        path = scope.get('path', '')
        if scope['type'] == 'http' and not scope.get('query_string') and (
            (scope['method'] == 'POST' and path in {'/firewall/save', '/firewall/read', '/firewall/list',
             '/api/firewall/login', '/api/firewall/logout', '/api/firewall/chat', '/api/firewall/chats',
             '/api/firewall/history', '/api/firewall/view'}) or
            (scope['method'] == 'GET' and (path == '/api/firewall/session' or path == '/' or
             re.fullmatch(r'/c/[a-f0-9-]{36}', path) or path.startswith('/_app/') or
             path in {'/static/favicon.png', '/static/favicon-96x96.png', '/static/favicon.svg',
                      '/static/favicon.ico', '/static/apple-touch-icon.png',
                      '/static/splash.png', '/static/splash-dark.png', '/manifest.json'}))):
            async def security_send(message):
                if message['type'] == 'http.response.start':
                    message['headers'] = list(message.get('headers', [])) + [
                        (b'content-security-policy', b"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"),
                        (b'x-content-type-options', b'nosniff'), (b'referrer-policy', b'no-referrer')]
                await send(message)
            return await protected_api(scope, receive, security_send)
        return await locked(scope, receive, send)
    return application
