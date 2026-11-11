"""Short-lived, scoped integrity receipts; keys belong to trusted ingress only."""
import hashlib
import hmac
import json
import secrets
import time


class Admission:
    def __init__(self, key: bytes, policy: str, clock=time.time):
        if len(key) < 32:
            raise ValueError("admission key must contain at least 32 bytes")
        self.key, self.policy, self.clock = key, policy, clock

    def issue(self, content: bytes, user: str, operation: str) -> str:
        claims = dict(hash=hashlib.sha256(content).hexdigest(), user=user,
                      operation=operation, policy=self.policy,
                      expires=int(self.clock()) + 30, nonce=secrets.token_hex(16))
        body = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode().hex()
        signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        return body + "." + signature

    def verify(self, token: str, content: bytes, user: str, operation: str) -> bool:
        try:
            if len(token) > 4096:
                return False
            body, signature = token.split(".")
            expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return False
            claims = json.loads(bytes.fromhex(body))
            return (claims["hash"] == hashlib.sha256(content).hexdigest()
                    and claims["user"] == user and claims["operation"] == operation
                    and claims["policy"] == self.policy
                    and self.clock() < claims["expires"] <= self.clock() + 30)
        except (ValueError, KeyError, TypeError, UnicodeError):
            return False