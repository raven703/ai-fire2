"""Staged native runtime: original UI/auth, content operations CLOSED.

This is deliberately not a protected-chat acceptance claim. The outer boundary
cannot be disabled by a client or the core development flag.
"""
import json
import re
import os
from contextlib import asynccontextmanager

from starlette.responses import JSONResponse

from open_webui.main import app as upstream
from ai_firewall.native_writer import install, protect_database

# Covers ORM writers regardless of REST/socket/internal caller. Content remains
# closed until permitted native lifecycle writes have their own acceptance.
install()
from ai_firewall.native_http import router as native_router
upstream.include_router(native_router)
# Upstream mounts its SPA at '/'; native routes must precede that catch-all.
native_paths = {route.path for route in native_router.routes}
upstream.router.routes[:] = ([route for route in upstream.router.routes if getattr(route, 'path', None) in native_paths]
                            + [route for route in upstream.router.routes if getattr(route, 'path', None) not in native_paths])


original_lifespan = upstream.router.lifespan_context


@asynccontextmanager
async def guarded_lifespan(app):
    # Install connection listeners before upstream starts reconciliation tasks;
    # changing an event deque concurrently with first connect is unsafe.
    from open_webui.internal.db import async_engine
    await protect_database(async_engine)
    async with original_lifespan(app) as state:
        yield state


upstream.router.lifespan_context = guarded_lifespan


class StagedNative:
    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await upstream(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        if scope['type'] != 'http':
            return
        path = scope['path']
        method = scope['method']
        auth_post = path in {'/api/v1/auths/signin', '/api/v1/auths/signup', '/api/v1/auths/signout'}
        public_get = path in {'/health', '/health/db', '/api/config', '/api/version', '/api/changelog',
                              '/api/v1/auths/', '/api/v1/users/user/settings', '/api/v1/users/user/permissions'}
        static_get = not path.startswith(('/api', '/ws', '/openai', '/ollama', '/oauth'))
        native_enabled = os.environ.get('FIREWALL_NATIVE_HTTP') == 'true'
        if native_enabled and method == 'GET' and path == '/api/config':
            captured = []
            async def capture(event):
                captured.append(event)
            config_scope = {**scope, 'headers': [(k, v) for k, v in scope.get('headers', []) if k.lower() != b'accept-encoding']}
            await upstream(config_scope, receive, capture)
            body = b''.join(e.get('body', b'') for e in captured if e['type'] == 'http.response.body')
            config = json.loads(body)
            config.setdefault('features', {})['native_text_only'] = True
            return await JSONResponse(config, headers={'Cache-Control': 'no-store'})(scope, receive, send)
        if native_enabled and method == 'GET' and re.fullmatch(r'/api/v1/chats/[a-f0-9-]{36}/view', path):
            # No saved auxiliary view state is enabled in protected text mode.
            return await JSONResponse({'state': None}, headers={'Cache-Control': 'no-store'})(scope, receive, send)
        if native_enabled and method == 'GET' and re.fullmatch(r'/api/v1/users/[a-f0-9-]{36}/profile/image', path):
            # Native mode does not expose uploaded/remote profile content.
            from starlette.responses import FileResponse
            return await FileResponse('/app/backend/open_webui/static/user.png')(scope, receive, send)
        # Unsupported discovery returns no capabilities; it does not invoke
        # upstream tools/terminal/task writers or expose their content.
        empty_discovery = {'/api/v1/tools/', '/api/v1/terminals/', '/api/v1/configs/banners',
                           '/api/v1/chats/all/tags', '/api/v1/notes/pinned', '/api/v1/chats/pinned',
                           '/api/v1/folders/', '/api/v1/folders/shared', '/api/v1/functions/',
                           '/api/v1/skills/'}
        if native_enabled and method == 'GET' and path in empty_discovery:
            return await JSONResponse([], headers={'Cache-Control': 'no-store'})(scope, receive, send)
        native_get = (path in {'/api/models/native', '/api/v1/chats/native/list', '/api/v1/users/', '/api/v1/groups/'}
                      or re.fullmatch(r'/api/v1/chats/[a-f0-9-]{36}(?:/native)?', path))
        native_delete = method == 'DELETE' and re.fullmatch(r'/api/v1/chats/[a-f0-9-]{36}', path)
        native_post = (path in {'/api/chat/completions/native','/api/v1/dlp/policies','/api/v1/files/native'} or
                       re.fullmatch(r'/api/v1/chats/[a-f0-9-]{36}/native/reveal', path))
        if not ((method == 'GET' and (public_get or static_get)) or (method == 'POST' and auth_post)
                or (native_enabled and ((method == 'GET' and native_get) or (method == 'POST' and native_post) or native_delete))):
            return await JSONResponse({'detail': 'native_content_not_accepted'}, status_code=503,
                                      headers={'Cache-Control': 'no-store'})(scope, receive, send)
        if method == 'POST':
            body = bytearray()
            while True:
                event = await receive()
                if event['type'] == 'http.disconnect':
                    return
                body.extend(event.get('body', b''))
                if len(body) > (10*1024*1024 if path=='/api/v1/files/native' else 8192):
                    return await JSONResponse({'detail': 'body_too_large'}, status_code=413)(scope, receive, send)
                if not event.get('more_body'):
                    break
            if path.endswith('/signup'):
                try:
                    data = json.loads(body)
                    # Synthetic staging identities only. Password never enters DLP.
                    if (set(data) - {'name', 'email', 'password', 'profile_image_url'}
                            or not re.fullmatch(r'Synthetic [A-Za-z0-9 ]{1,40}', data.get('name', ''))
                            or not re.fullmatch(r'[a-z0-9]{1,64}@synthetic\.invalid', data.get('email', ''))
                            or data.get('profile_image_url') not in {None, '/user.png'}):
                        raise ValueError()
                except Exception:
                    return await JSONResponse({'detail': 'synthetic_identity_required'}, status_code=400)(scope, receive, send)
            delivered = False
            original_receive = receive

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await original_receive()

            receive = replay

        async def safe_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [(k, v) for k, v in message.get('headers', [])
                                      if k.lower() != b'cache-control'] + [(b'cache-control', b'no-store')]
            await send(message)

        # Never rethrow payload-bearing exceptions into uvicorn's traceback logs.
        started = False

        async def tracked_send(message):
            nonlocal started
            if message['type'] == 'http.response.start':
                started = True
            await safe_send(message)

        try:
            await upstream(scope, receive, tracked_send)
        except Exception:
            if not started:
                await JSONResponse({'detail': 'native_processing_failed'}, status_code=503,
                                   headers={'Cache-Control': 'no-store'})(scope, receive, send)


app = StagedNative()