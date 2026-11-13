"""Envelope encryption using existing Transit pii KEK; no additional key authority.

SQLite commits the encrypted envelope atomically in a dedicated persistent volume.
Only wrapped random per-object keys are persisted; AAD binds every immutable field.
"""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encoded(value):return base64.b64encode(value).decode()

@contextmanager
def database():
    root=Path(os.getenv('EVIDENCE_ROOT','/evidence'));root.mkdir(mode=0o700,parents=True,exist_ok=True)
    db=sqlite3.connect(root/'ciphertext.db',timeout=15)
    db.execute('PRAGMA secure_delete=ON')
    db.executescript('''CREATE TABLE IF NOT EXISTS objects(id TEXT PRIMARY KEY,metadata TEXT,wrapped TEXT,nonce BLOB,ciphertext BLOB);
    CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,timestamp REAL,actor TEXT,object TEXT,operation TEXT,result TEXT);''')
    try:
        with db:yield db
    finally:db.close()

def access(db,actor,identifier,operation,result):
    db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',(str(uuid4()),time.time(),actor,identifier,operation,result))

def cleanup(db):
    for identifier,metadata in db.execute('SELECT id,metadata FROM objects').fetchall():
        if json.loads(metadata)['expires']<=time.time():
            db.execute('DELETE FROM objects WHERE id=?',(identifier,))
            access(db,'system',identifier,'TTL_DELETE','SUCCESS')

def store(raw,context,limits,bao):
    identifier=str(uuid4())
    if len(raw)>limits['max_bytes']:raise ValueError('EVIDENCE_SIZE_LIMIT')
    metadata=dict(evidence_id=identifier,event_id=context['event_id'],user_id=context['user_id'],
        chat_id=context['chat_id'],policy_revision=context.get('policy_revision'),
        sha256=hashlib.sha256(raw).hexdigest(),extension=context['extension'],
        expires=int(time.time()+limits['retention_days']*86400),size=len(raw))
    aad=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()
    key=AESGCM.generate_key(bit_length=256);nonce=secrets.token_bytes(12)
    ciphertext=AESGCM(key).encrypt(nonce,raw,aad)
    wrapped=bao('encrypt/pii',{'plaintext':encoded(key),'associated_data':encoded(aad)})['ciphertext']
    with database() as db:
        db.execute('BEGIN IMMEDIATE');cleanup(db)
        used=db.execute('SELECT COALESCE(SUM(length(ciphertext)),0) FROM objects').fetchone()[0]
        if used+len(ciphertext)>limits['quota_bytes']:raise ValueError('EVIDENCE_QUOTA_EXCEEDED')
        db.execute('INSERT INTO objects VALUES(?,?,?,?,?)',(identifier,aad.decode(),wrapped,nonce,ciphertext))
        access(db,context['user_id'],identifier,'STORE','SUCCESS')
    return dict(id=identifier,status='STORED',expires=metadata['expires'])

def retrieve(identifier,event_id,actor,bao):
    with database() as db:
        cleanup(db)
        row=db.execute('SELECT metadata,wrapped,nonce,ciphertext FROM objects WHERE id=?',(identifier,)).fetchone()
        access(db,actor,identifier,'DECRYPT','ATTEMPT')
    try:
        if not row:raise ValueError()
        metadata=json.loads(row[0])
        if metadata['event_id']!=event_id or metadata['evidence_id']!=identifier:raise ValueError()
        aad=row[0].encode()
        key=base64.b64decode(bao('decrypt/pii',{'ciphertext':row[1],'associated_data':encoded(aad)})['plaintext'],validate=True)
        raw=AESGCM(key).decrypt(row[2],row[3],aad)
        if hashlib.sha256(raw).hexdigest()!=metadata['sha256']:raise ValueError()
    except Exception:
        with database() as db:access(db,actor,identifier,'DECRYPT','FAILED')
        raise ValueError('evidence_unavailable') from None
    with database() as db:access(db,actor,identifier,'DECRYPT','SUCCESS')
    return raw,metadata