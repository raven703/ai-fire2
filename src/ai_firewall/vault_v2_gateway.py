"""Isolated synthetic Vault migration Gateway, not enabled in Native runtime."""
import os
import re
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Request
from ai_firewall.protocol import harden, schema
from ai_firewall.vault_v2 import authorize, scope

app=FastAPI()


@app.post('/inspect')
def inspect(request:Request,data:dict):
    authorize(request,'VAULT_WRITE_KEY_FILE')
    schema(data,{'tenant','user','chat','fields'})
    context={k:data[k] for k in ('tenant','user','chat')}; scope(context)
    fields=data['fields']
    if not isinstance(fields,dict) or not 1<=len(fields)<=128 or any(not isinstance(v,str) or len(v)>8000 for v in fields.values()):
        raise HTTPException(400,'invalid_fields')
    # Full batch verdict before the first store call. No arbitrary PII accepted.
    if any('SYNTHETIC_BLOCK_' in v for v in fields.values()): raise HTTPException(403,'BLOCK')
    if any('SYNTHETIC_REVIEW_' in v for v in fields.values()): raise HTTPException(403,'REVIEW')
    matches=[(name,m) for name,value in fields.items() for m in re.finditer(r'SYNTHETIC_V2_[A-Za-z0-9_]{1,200}',value)]
    if not matches: return {'fields':fields,'action':'ALLOW'}
    try:
        with httpx.Client(timeout=5,trust_env=False) as client:
            result=client.post('http://vault-v2:8000/store-batch',headers={
                'Authorization':'Bearer '+Path(os.environ['VAULT_WRITE_KEY_FILE']).read_text().strip()},
                json={**context,'values':[m.group() for _,m in matches],
                    'verdict':'MASK','policy_version':'synthetic-evaluation-v1'})
            result.raise_for_status(); tokens=result.json()['tokens']
        cleaned=dict(fields)
        for (name,m),token in reversed(list(zip(matches,tokens,strict=True))):
            cleaned[name]=cleaned[name][:m.start()]+token+cleaned[name][m.end():]
        return {'fields':cleaned,'action':'MASK'}
    except Exception: raise HTTPException(503,'vault_unavailable') from None


app=harden(app)