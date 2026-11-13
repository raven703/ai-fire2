"""Content-free durable state and atomic single-consumer claims."""
import hashlib
import json
import time
from uuid import uuid4
from fastapi import HTTPException
from ai_firewall import dlp_events as events


def init(db):
    db.executescript('''CREATE TABLE IF NOT EXISTS review_permissions(user TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS reviews(id TEXT PRIMARY KEY,user TEXT,chat TEXT,policy TEXT,
      digest TEXT,evidence TEXT,expires REAL,state TEXT);
    CREATE TABLE IF NOT EXISTS review_actions(id TEXT PRIMARY KEY,event TEXT,at REAL,actor TEXT,action TEXT,reason TEXT);''')


def permitted(user):
    with events.database() as db:
        init(db)
        return db.execute('SELECT 1 FROM review_permissions WHERE user=?',(user,)).fetchone() is not None


def register(event, raw):
    if event['action']!='REVIEW' or event['evidence'].get('status')!='STORED':return
    e=event['evidence']
    with events.database() as db:
        init(db)
        db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?)',(event['event_id'],event['user_id'],event['chat_id'],
            event['policy_revision'],hashlib.sha256(raw).hexdigest(),e['id'],e['expires'],'PENDING'))


def get(identifier):
    with events.database() as db:
        init(db)
        db.execute("UPDATE reviews SET state='EXPIRED' WHERE id=? AND expires<=? AND state IN ('PENDING','APPROVED')",(identifier,time.time()))
        row=db.execute('SELECT * FROM reviews WHERE id=?',(identifier,)).fetchone()
        history=db.execute('SELECT at,actor,action,reason FROM review_actions WHERE event=? ORDER BY at',(identifier,)).fetchall()
    if not row:return None
    return {**dict(zip(('id','user','chat','policy','digest','evidence','expires','state'),row)),
            'history':[dict(zip(('at','actor','action','reason'),r)) for r in history]}


def move(identifier, old, new, actor, reason=''):
    with events.database() as db:
        init(db)
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('UPDATE reviews SET state=? WHERE id=? AND state=? AND expires>?',
            (new,identifier,old,time.time())).rowcount:
            raise HTTPException(409,'review_state_conflict')
        db.execute('INSERT INTO review_actions VALUES(?,?,?,?,?,?)',(uuid4().hex,identifier,time.time(),actor,new,reason))
        db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',(uuid4().hex,time.time(),actor,identifier,'REVIEW_'+new,'SUCCESS'))


def validate(review,raw):
    try:
        if hashlib.sha256(raw).hexdigest()!=review['digest']:raise ValueError()
        saved=json.loads(raw)
        if any(saved[k]!=review[k] for k in ('user','chat','policy')) or saved['tenant']!='synthetic':raise ValueError()
        return saved
    except Exception:raise HTTPException(409,'review_evidence_invalid') from None


def public(review):
    return {k:review[k] for k in ('id','state','expires','history')} if review else None