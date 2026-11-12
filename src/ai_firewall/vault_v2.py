"""Synthetic-only encrypted mapping store. No plaintext logging or local keys."""
import base64
import json
import os
import re
import secrets
import time
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI, HTTPException, Request
from ai_firewall.protocol import harden, schema
from ai_firewall.synthetic_v2 import permitted_values

SYNTHETIC_VALUES=permitted_values()


def secret(name): return Path(os.environ[name]).read_text().strip()


def authorize(request, name):
    if not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+secret(name)):
        raise HTTPException(403,'denied')


def bao(path,data):
    try:
        with httpx.Client(timeout=4,trust_env=False,verify=os.environ.get('BAO_CA',True)) as client:
            response=client.post(os.environ['BAO_URL']+'/v1/transit/'+path,json=data,
                headers={'X-Vault-Token':secret('BAO_DECRYPT_TOKEN_FILE' if path.startswith('decrypt/') else 'BAO_TOKEN_FILE')})
            response.raise_for_status()
            return response.json()['data']
    except Exception: raise HTTPException(503,'key_service_unavailable') from None


def encoded(value): return base64.b64encode(value.encode()).decode()
def packed(value): return json.dumps(value,sort_keys=True,separators=(',',':'))


def scope(data):
    value=[data[k] for k in ('tenant','user','chat')]
    if any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',v) for v in value):
        raise HTTPException(400,'invalid_scope')
    return packed(value)


def connection():
    return psycopg.connect(host='postgres',dbname='vault',user='vault',password=secret('PG_PASSWORD_FILE'),connect_timeout=4)


def aad(context,token,expires): return encoded(packed([context,token,expires]))


app=FastAPI()


@app.get('/health')
def health():
    # Readiness includes both dependencies, not just process liveness.
    bao('hmac/lookup',{'input':encoded('readiness')})
    with connection() as db: db.execute('SELECT 1')
    return {'ready':True}


@app.post('/store-batch')
def store(request:Request,data:dict):
    authorize(request,'VAULT_WRITE_KEY_FILE')
    schema(data,{'tenant','user','chat','values','verdict','policy_version'}, {'policy_revision','mask_approval'})
    context=scope(data)
    if data['verdict']!='MASK' or data['policy_version']!='synthetic-evaluation-v1':
        raise HTTPException(403,'final_mask_required')
    values=data['values']
    if (not isinstance(values,list) or not 1<=len(values)<=128
            or any(not isinstance(v,str) or not 1<=len(v)<=16384 for v in values)
            or sum(len(v.encode()) for v in values)>128000):
        raise HTTPException(400,'invalid_values')
    if os.getenv('MASK_ATTESTATION_KEY_FILE'):
        from ai_firewall.mask_attestation import verify
        if data['tenant']!='synthetic' or not verify(secret('MASK_ATTESTATION_KEY_FILE'),data.get('mask_approval'),data['user'],data['chat'],data.get('policy_revision'),values):
            raise HTTPException(403,'mask_approval_required')
    # Deliberately prohibit real PII in this acceptance contour, irrespective of
    # Gateway caller claims. A separate migration is required to remove this gate.
    approved_general=(os.getenv('MASK_ATTESTATION_KEY_FILE') and
        (data.get('mask_approval',{}).get('synthetic') is True or os.getenv('DLP_REAL_DATA_ENABLED')=='true'))
    if not approved_general and (not isinstance(values,list) or not 1<=len(values)<=128 or
            any(not isinstance(v,str) or not (re.fullmatch(r'SYNTHETIC_V2_[A-Za-z0-9_]{1,200}',v)
                or v in SYNTHETIC_VALUES) for v in values)):
        raise HTTPException(403,'synthetic_v2_fixture_required')
    ttl=int(os.environ.get('VAULT_V2_TTL','300'))
    if not 1<=ttl<=86400: raise HTTPException(503,'invalid_ttl')
    tokens=[]
    with connection() as db:
        # Serialize scoped reuse and ensure all writes are one transaction.
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(context,))
        for value in values:
            lookup=bao('hmac/lookup',{'input':encoded(packed([context,value]))})['hmac']
            row=db.execute('SELECT token,expires FROM mappings WHERE scope=%s AND lookup=%s FOR UPDATE',(context,lookup)).fetchone()
            now=int(time.time())
            if row and row[1]>now:
                tokens.append(row[0]); continue
            if row: db.execute('DELETE FROM mappings WHERE token=%s',(row[0],))
            token='[V2_'+secrets.token_hex(32)+']'; expires=now+ttl
            ciphertext=bao('encrypt/pii',{'plaintext':encoded(value),'associated_data':aad(context,token,expires)})['ciphertext']
            db.execute('INSERT INTO mappings(token,scope,lookup,ciphertext,expires) VALUES(%s,%s,%s,%s,%s)',
                (token,context,lookup,ciphertext,expires))
            tokens.append(token)
    return {'tokens':tokens}


@app.post('/reveal')
def reveal(request:Request,data:dict):
    authorize(request,'VAULT_REVEAL_KEY_FILE')
    schema(data,{'tenant','user','chat','tokens'})
    context=scope(data)
    if not isinstance(data['tokens'],list) or not 1<=len(data['tokens'])<=128: raise HTTPException(400,'invalid_tokens')
    result={}
    with connection() as db:
        for token in data['tokens']:
            if not isinstance(token,str) or not re.fullmatch(r'\[V2_[a-f0-9]{64}\]',token): raise HTTPException(400,'invalid_token')
            row=db.execute('SELECT ciphertext,expires FROM mappings WHERE token=%s AND scope=%s',(token,context)).fetchone()
            if not row or row[1]<=time.time(): raise HTTPException(404,'mapping_unavailable')
            clear=bao('decrypt/pii',{'ciphertext':row[0],'associated_data':aad(context,token,row[1])})['plaintext']
            result[token]=base64.b64decode(clear,validate=True).decode()
    return {'values':result}


@app.post('/delete-context')
def delete(request:Request,data:dict):
    authorize(request,'VAULT_WRITE_KEY_FILE')
    schema(data,{'tenant','user','chat'})
    with connection() as db: db.execute('DELETE FROM mappings WHERE scope=%s OR expires<=%s',(scope(data),int(time.time())))
    return {'deleted':True}


@app.post('/cleanup-expired')
def cleanup_expired(request:Request,data:dict):
    """Bounded orphan retention without guessing whether a token is referenced.

    A failed WebUI commit leaves a mapping until its normal expiry. Only already
    irreversibly expired rows may be reclaimed; shared live tokens are untouched.
    SKIP LOCKED avoids interfering with concurrent STORE transactions.
    """
    authorize(request,'VAULT_WRITE_KEY_FILE')
    schema(data,set())
    with connection() as db:
        rows=db.execute('WITH expired AS (SELECT token FROM mappings WHERE expires<=%s '
            'ORDER BY expires LIMIT 500 FOR UPDATE SKIP LOCKED) '
            'DELETE FROM mappings USING expired WHERE mappings.token=expired.token '
            'RETURNING mappings.token',(int(time.time()),)).fetchall()
    return {'deleted_count':len(rows)}


app=harden(app)