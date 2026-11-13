"""Strict synthetic POC protocol shared by trusted processes (never browser history)."""
import hashlib
import hmac
import json
import os
import uuid

from fastapi import HTTPException
from starlette.responses import JSONResponse

USERS = {'synthetic-user': 'USER_KEY', 'synthetic-bob': 'USER_B_KEY'}


def identity(request):
    supplied = request.headers.get('authorization', '')
    for user, name in USERS.items():
        value = os.getenv(name, '')
        if len(value) >= 32 and hmac.compare_digest(supplied, 'Bearer ' + value):
            return user
    raise HTTPException(403, 'authentication_required')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def version(messages):
    return hashlib.sha256(canonical(messages)).hexdigest()


def schema(data, required, optional=()):
    if not isinstance(data, dict) or not set(required) <= set(data) or set(data) - set(required) - set(optional):
        raise HTTPException(400, 'invalid_schema')


def context(user, chat):
    if user not in USERS or not isinstance(chat, str):
        raise HTTPException(403, 'scope_denied')
    try:
        if str(uuid.UUID(chat)) != chat:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, 'invalid_chat_id') from None


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 8000 or '\x00' in value:
        raise HTTPException(400, 'invalid_text')
    return value


def harden(app, *, body_limit=262144):
    """Bound body before parsing and never return/log exception payloads."""
    @app.exception_handler(Exception)
    async def unexpected(request, error):
        return JSONResponse({'detail': 'processing_failed'}, status_code=503,
                            headers={'Cache-Control': 'no-store'})

    @app.exception_handler(HTTPException)
    async def denied(request, error):
        return JSONResponse({'detail': error.detail}, status_code=error.status_code,
                            headers={'Cache-Control': 'no-store'})

    class Bounded:
        async def __call__(self, scope, receive, send):
            if scope['type'] != 'http':
                if scope['type'] == 'websocket':
                    return await send({'type': 'websocket.close', 'code': 1008})
                return await app(scope, receive, send)
            body = bytearray()
            while True:
                event = await receive()
                if event['type'] == 'http.disconnect':
                    return
                body.extend(event.get('body', b''))
                if len(body) > body_limit:
                    return await JSONResponse({'detail': 'body_too_large'}, status_code=413)(scope, receive, send)
                if not event.get('more_body'):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()

            async def safe_send(message):
                if message['type'] == 'http.response.start':
                    message['headers'] = [(k, v) for k, v in message.get('headers', [])
                                          if k.lower() != b'cache-control'] + [(b'cache-control', b'no-store')]
                await send(message)
            try:
                await app(scope, replay, safe_send)
            except Exception:
                # ServerErrorMiddleware already emitted the generic response. Suppress
                # re-raising to uvicorn, whose traceback could contain detector data.
                return
    return Bounded()