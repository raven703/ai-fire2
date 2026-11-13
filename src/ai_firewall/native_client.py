"""Backend-only native admission client. Never accepts a browser-issued permit."""
from contextvars import ContextVar

pinned_file_policy = ContextVar("pinned_file_policy", default=None)
review_execution = ContextVar('review_execution', default=None)

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
        self.policy_revision = pinned_file_policy.get()

    async def inspect(self, fields, user, chat, operation, revision, *, receipt=False):
        correlation=uuid4().hex
        self.correlation_id=correlation
        self.diagnostics={}
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
                    if isinstance(verdict,dict) and verdict.get('action') in {'BLOCK','REVIEW'}:
                        self.diagnostics=verdict
                        raise HTTPException(403,verdict['action'])
                    if isinstance(verdict,str) and verdict in {'BLOCK', 'REVIEW'}: raise HTTPException(403, verdict)
                raise HTTPException(403 if response.status_code == 403 else 503, 'native_inspection_denied')
            result = response.json()
            self.diagnostics={k:result.get(k) for k in ('action','categories','findings','policy_version','policy_revision')}
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
            # Native runtime only: standalone gateway/unit images have no events DB.
            if operation=='input' and __import__('os').getenv('FIREWALL_NATIVE_HTTP')=='true':
                from ai_firewall import dlp_events as events
                d=self.diagnostics
                event=events.create(user_id=user,chat_id=chat,source='CHAT',
                    action=d.get('action') or 'TECHNICAL_FAILURE',reason_code=('POLICY_'+d['action']) if d.get('action') else 'DEPENDENCY_UNAVAILABLE',
                    policy_version=d.get('policy_version'),policy_revision=d.get('policy_revision'),
                    processing_ms=round((time.monotonic()-started)*1000))
                event.update(correlation_id=correlation,categories=d.get('categories') or [],
                    findings=d.get('findings') or [],match_count=len(d.get('findings') or []))
                events.put(event)
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

    async def review_model(self, saved, user, chat):
        from ai_firewall.review_contract import scope,issue
        if saved['user']!=user or saved['chat']!=chat:raise HTTPException(403,'review_scope_invalid')
        fields={'content':saved['turn']['content']}
        claims=scope(saved['event'],fields,user,chat,saved['policy'])
        import os
        token=issue(os.environ['ADMISSION_KEY'],claims)
        async with httpx.AsyncClient(timeout=15,trust_env=False,transport=self.transport) as client:
            response=await client.post(self.url+'/native/review-model',headers={'Authorization':'Bearer '+self.service_key},
                json={'event':saved['event'],'fields':fields,'user':user,'chat':chat,'policy':saved['policy'],'permit':token})
        if response.status_code!=200:raise HTTPException(403,'review_model_denied')
        result=response.json()
        if result.get('fields')!=fields or result.get('policy_revision')!=saved['policy']:raise HTTPException(503,'review_receipt_invalid')
        return result['fields']['content']

    async def delta(self,fields,delta,before,user,chat,current_revision):
        import json
        payload=dict(fields=fields,before=before,delta=delta,user=user,chat=chat,operation='chat-delta',revision=current_revision)
        async with httpx.AsyncClient(timeout=15,trust_env=False,transport=self.transport) as client:
            response=await client.post(self.url+'/native/delta-permit',headers={'Authorization':'Bearer '+self.service_key},
                json={'payload':payload,'delta':json.dumps(delta,sort_keys=True,separators=(',',':'))})
        if response.status_code!=200:raise HTTPException(403,'native_delta_denied')
        result=response.json()
        if result.get('payload')!=payload or not self.receipts.verify(result['admission'],canonical(payload),user,'chat-delta'):
            raise HTTPException(503,'native_delta_receipt_invalid')
        return result


def revision(value):
    return hashlib.sha256(canonical(value)).hexdigest()