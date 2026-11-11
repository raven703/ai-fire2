"""Staged native runtime: original UI/auth, content operations CLOSED.

This is deliberately not a protected-chat acceptance claim. The outer boundary
cannot be disabled by a client or the core development flag.
"""
import json
import re

from starlette.responses import JSONResponse

from open_webui.main import app as upstream
from ai_firewall.native_writer import install

# Covers ORM writers regardless of REST/socket/internal caller. Content remains
# closed until permitted native lifecycle writes have their own acceptance.
install()


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
        if not ((method == 'GET' and (public_get or static_get)) or (method == 'POST' and auth_post)):
            return await JSONResponse({'detail': 'native_content_not_accepted'}, status_code=503,
                                      headers={'Cache-Control': 'no-store'})(scope, receive, send)
        if method == 'POST':
            body = bytearray()
            while True:
                event = await receive()
                if event['type'] == 'http.disconnect':
                    return
                body.extend(event.get('body', b''))
                if len(body) > 8192:
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