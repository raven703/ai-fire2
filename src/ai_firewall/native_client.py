"""Backend-only native admission client. Never accepts a browser-issued permit."""
import hashlib
import logging
import time
from uuid import uuid4

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
        self.policy_revision = None

    async def inspect(self, fields, user, chat, operation, revision, *, receipt=False):
        correlation=uuid4().hex
        started=time.monotonic()
        status=503
        payload = dict(fields=fields, user=user, chat=chat, operation=operation, revision=revision)
        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False, transport=self.transport) as client:
                response = await client.post(self.url + '/native/inspect', json=payload,
                                             headers={'Authorization': 'Bearer ' + self.service_key,
                                                      'X-Policy-Revision': self.policy_revision or '',
                                                      'X-Correlation-ID': correlation})
            status=response.status_code
            if response.status_code != 200:
                if response.status_code == 403:
                    try: verdict = response.json().get('detail')
                    except Exception: verdict = None
                    if verdict in {'BLOCK', 'REVIEW'}: raise HTTPException(403, verdict)
                raise HTTPException(403 if response.status_code == 403 else 503, 'native_inspection_denied')
            result = response.json()
            policy_revision=result.get('policy_revision')
            if self.policy_revision and policy_revision!=self.policy_revision:
                raise ValueError('policy_revision_changed')
            if policy_revision: self.policy_revision=policy_revision
            approved = result['payload']
            if (set(approved) != set(payload)
                    or any(approved[k] != payload[k] for k in payload if k != 'fields')
                    or set(approved['fields']) != set(fields)
                    or not all(isinstance(v, str) for v in approved['fields'].values())
                    or result['action'] not in {'ALLOW', 'MASK'}
                    or not self.receipts.verify(result['admission'], canonical(approved), user, operation)):
                raise ValueError('invalid_receipt')
            return result if receipt else approved['fields']
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, 'native_inspection_unavailable') from None
        finally:
            logging.getLogger('uvicorn.error').warning(
                'dlp_trace correlation=%s stage=%s status=%s duration_ms=%s source=gateway',
                correlation,operation,status,round((time.monotonic()-started)*1000))

    async def deletion(self,fields,user,chat,current_revision):
        from ai_firewall.delete_contract import validate_delete
        payload=validate_delete(dict(fields=fields,user=user,chat=chat,operation='chat-delete',revision=current_revision))
        try:
            async with httpx.AsyncClient(timeout=10,trust_env=False,transport=self.transport) as client:
                response=await client.post(self.url+'/native/delete-permit',json=payload,
                    headers={'Authorization':'Bearer '+self.service_key})
            response.raise_for_status()
            result=response.json()
            if result['payload']!=payload or not self.receipts.verify(result['admission'],canonical(payload),user,'chat-delete'):
                raise ValueError()
            return result
        except Exception: raise HTTPException(503,'native_delete_permit_unavailable') from None


def revision(value):
    return hashlib.sha256(canonical(value)).hexdigest()