"""Isolated test-only NLP worker. Stateless masks; never calls plaintext Vault."""
import os
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from ai_firewall.services import auth
from ai_firewall.protocol import harden, schema, text
from ai_firewall.detection import DetectorPipeline, PolicyContext, Action
from ai_firewall.pii_engine import create_pipeline
from ai_firewall.pii_policy import YAMLPolicy, inspect_object


@asynccontextmanager
async def lifespan(app):
    import anyio
    # One model execution at a time; host timeout bounds admission latency,
    # container limits bound a worker that fails to finish.
    anyio.to_thread.current_default_thread_limiter().total_tokens=1
    if os.getenv('PII_TEST_ONLY')!='true': raise RuntimeError('test_only_required')
    for line in Path('/app/config/pii-models.sha256').read_text().splitlines():
        digest,path=line.split(maxsplit=1)
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('invalid_local_model')
    policy=YAMLPolicy('/app/config/pii-policy-v1.yaml')
    base=create_pipeline()
    app.state.pipeline=DetectorPipeline([*base.detectors,*policy.detectors])
    app.state.policy=policy
    app.state.pipeline.inspect('Проверка готовности')
    yield


app=FastAPI(lifespan=lifespan)
worker=app


@app.get('/health')
def health(): return {'ready':True,'policy_version':worker.state.policy.version}


@app.post('/inspect')
def inspect(request: Request, data: dict):
    auth(request,'NATIVE_GATEWAY_KEY')
    schema(data,{'fields','operation'})
    fields=data['fields']
    if not isinstance(fields,dict) or not 1<=len(fields)<=256: raise HTTPException(400,'invalid_fields')
    values={k:text(v) for k,v in fields.items()}
    if sum(map(len,values.values()))>128000: raise HTTPException(413,'batch_too_large')
    try:
        if os.getenv('PII_MODEL_FAILURE')=='1': raise RuntimeError()
        policy=worker.state.policy
        action,decisions=inspect_object(values,worker.state.pipeline,policy,
            PolicyContext('synthetic-test','synthetic-test',data['operation'],policy.version))
        if action in {Action.BLOCK,Action.REVIEW}: raise HTTPException(403,action.value)
        cleaned=dict(values); categories=set()
        for name,decision in decisions.items():
            for span in reversed(decision.spans):
                categories.update(f.entity_type for f in span.findings)
                # Irreversible, scoped to this result; no original retained anywhere.
                cleaned[name]=cleaned[name][:span.start]+'[DLP_REDACTED]'+cleaned[name][span.end:]
        return {'fields':cleaned,'action':action.value,'categories':sorted(categories),'policy_version':policy.version,
            'spans':{name:[{'start':s.start,'end':s.end} for s in decision.spans] for name,decision in decisions.items()}}
    except HTTPException: raise
    except Exception: raise HTTPException(503,'mandatory_nlp_failed') from None


app=harden(app)