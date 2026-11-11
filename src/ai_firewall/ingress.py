"""Pure ASGI gate: bounded body before upstream parsing, logging or storage.

Production default denies every data path. An injected inspector is a test seam,
not a substitute for mandatory detectors or authenticated gateway transport.
"""
import json

from starlette.responses import JSONResponse


class ProtectedIngress:
    def __init__(self, app, inspector=None, max_bytes=16384):
        self.app, self.inspector, self.max_bytes = app, inspector, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            return

        async def reject(status):
            await JSONResponse({"detail": "firewall_denied"}, status_code=status)(scope, receive, send)

        if scope["path"] == "/health" and scope["method"] == "GET":
            return await JSONResponse({"status": "locked", "production_ready": False})(scope, receive, send)
        if (self.inspector is None or scope["method"] != "POST"
                or scope["path"] != "/api/v1/chats/new" or scope.get("query_string")):
            return await reject(403)
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] == "http.disconnect":
                return
            body.extend(event.get("body", b""))
            if len(body) > self.max_bytes:
                return await reject(413)
            if not event.get("more_body", False):
                break
        try:
            payload = json.loads(body)
            # Only a deliberately small, single-line chat schema is proved.
            if (not isinstance(payload, dict) or set(payload) != {"chat"}
                    or not isinstance(payload["chat"], dict)
                    or set(payload["chat"]) != {"title"}
                    or not isinstance(payload["chat"]["title"], str)
                    or any(c in payload["chat"]["title"] for c in "\r\n")):
                return await reject(403)
            if await self.inspector(bytes(body), scope) is not True:
                return await reject(403)
        except Exception:
            # Never log exception text: a parser or detector can include payload.
            return await reject(503)
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)