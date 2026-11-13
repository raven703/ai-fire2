"""Encrypted, scoped, short-lived safe representations; no original storage."""
from contextlib import closing
import json
import os
import sqlite3
import time
from uuid import uuid4
from cryptography.fernet import Fernet
import base64
import hashlib
from fastapi import HTTPException


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((os.environ['ADMISSION_KEY']+'file-context-v1').encode()).digest()))


def db():
    connection=sqlite3.connect('/app/backend/data/native-file-context.db',timeout=10)
    connection.execute('CREATE TABLE IF NOT EXISTS contexts(id TEXT PRIMARY KEY,user TEXT,chat TEXT,policy TEXT,expires INTEGER,body BLOB)')
    connection.execute('DELETE FROM contexts WHERE expires<=?',(int(time.time()),))
    return connection


def save(user,chat,policy,fields,metadata=None):
    identifier=str(uuid4())
    with closing(db()) as connection, connection:
        connection.execute('INSERT INTO contexts VALUES(?,?,?,?,?,?)',(identifier,user,chat,policy,int(time.time())+900,cipher().encrypt(json.dumps({"fields":fields,"metadata":metadata or []}).encode())))
    return identifier


def load(identifier,user,chat,policy):
    with closing(db()) as connection, connection:
        row=connection.execute('SELECT body FROM contexts WHERE id=? AND user=? AND chat=? AND policy=? AND expires>?',(identifier,user,chat,policy,int(time.time()))).fetchone()
    if not row:raise HTTPException(409,'file_scope_expired_or_policy_changed')
    return json.loads(cipher().decrypt(row[0]))['fields']
