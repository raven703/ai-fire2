"""Backend-only native admission client. Never accepts a browser-issued permit."""
import hashlib

import httpx
from fastapi import HTTPException

from ai_firewall.admission import Admission
from ai_firewall.protocol import canonical


class NativeInspector:
    def __init__(self, url, service_key, admission_key, transport=None):
        self.url = url
        self.service_key = service_key
        self.receipts = Admission(admission_key.encode(), 'synthetic-v2')
        self.transport = transport

    async def inspect(self, fields, user, chat, operation, revision):
        payload = dict(fields=fields, user=user, chat=chat, operation=operation, revision=revision)
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False, transport=self.transport) as client:
                response = await client.post(self.url + '/native/inspect', json=payload,
                                             headers={'Authorization': 'Bearer ' + self.service_key})
            if response.status_code != 200:
                raise HTTPException(403 if response.status_code == 403 else 503, 'native_inspection_denied')
            result = response.json()
            approved = result['payload']
            if (set(approved) != set(payload)
                    or any(approved[k] != payload[k] for k in payload if k != 'fields')
                    or set(approved['fields']) != set(fields)
                    or not all(isinstance(v, str) for v in approved['fields'].values())
                    or result['action'] not in {'ALLOW', 'MASK'}
                    or not self.receipts.verify(result['admission'], canonical(approved), user, operation)):
                raise ValueError('invalid_receipt')
            return approved['fields']
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, 'native_inspection_unavailable') from None


def revision(value):
    return hashlib.sha256(canonical(value)).hexdigest()