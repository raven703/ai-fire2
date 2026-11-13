"""Versioned content-free decisions and evidence references. Native-only database."""
from contextlib import contextmanager
import json
import os
import sqlite3
import time
from uuid import uuid4

DEFAULTS=dict(enabled=False,store_block=True,store_review=True,store_technical=False,
              retention_days=7,max_bytes=10485760,quota_bytes=268435456)

@contextmanager
def database():
    path=os.getenv('DLP_EVENTS_DB','/app/backend/data/dlp-events.db')
    db=sqlite3.connect(path,timeout=15)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, timestamp REAL, body TEXT);
    CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, body TEXT);
    CREATE TABLE IF NOT EXISTS permissions(user TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,timestamp REAL,actor TEXT,object TEXT,operation TEXT,result TEXT);''')
    try:
        with db:yield db
    finally:db.close()

def settings():
    with database() as db:row=db.execute('SELECT body FROM settings WHERE id=1').fetchone()
    return json.loads(row[0]) if row else dict(DEFAULTS)

def audit(actor,object_id,operation,result):
    with database() as db:db.execute('INSERT INTO audit VALUES(?,?,?,?,?,?)',(str(uuid4()),time.time(),actor,object_id,operation,result))

def can_view(user):
    with database() as db:return db.execute('SELECT 1 FROM permissions WHERE user=?',(user,)).fetchone() is not None

def reconcile_pending():
    # A previous process may have died between durable writes. Never claim success.
    with database() as db:
        for identifier,body in db.execute('SELECT id,body FROM events').fetchall():
            event=json.loads(body)
            if event.get('evidence',{}).get('status')=='PENDING':
                event['evidence']={'status':'FAILED','reason_code':'INTERRUPTED_WRITE'}
                db.execute('UPDATE events SET body=? WHERE id=?',(json.dumps(event),identifier))

def create(**fields):
    event=dict(schema_version='1.0',event_id=str(uuid4()),timestamp=time.time(),
        correlation_id=str(uuid4()),tenant_id=None,findings=[],categories=[],match_count=0,
        evidence={'status':'DISABLED'},mock_result='NOT_SENT')
    event.update(fields)
    put(event)
    return event

def put(event):
    with database() as db:db.execute('INSERT OR REPLACE INTO events VALUES(?,?,?)',
        (event['event_id'],event['timestamp'],json.dumps(event,separators=(',',':'))))

def get(identifier):
    with database() as db:row=db.execute('SELECT body FROM events WHERE id=?',(identifier,)).fetchone()
    return json.loads(row[0]) if row else None

def query(filters):
    with database() as db:rows=db.execute('SELECT body FROM events ORDER BY timestamp DESC').fetchall()
    events=[json.loads(row[0]) for row in rows]
    for key in ('user_id','action','source','reason_code','policy_revision'):
        if filters.get(key):events=[e for e in events if e.get(key)==filters[key]]
    if filters.get('category'):events=[e for e in events if filters['category'] in e.get('categories',[])]
    for key,operator in (('since',lambda a,b:a>=b),('until',lambda a,b:a<=b)):
        if filters.get(key):events=[e for e in events if operator(e['timestamp'],float(filters[key]))]
    if filters.get('sort')=='asc':events.reverse()
    counts={a:sum(e['action']==a for e in events) for a in ('ALLOW','MASK','BLOCK','REVIEW','TECHNICAL_FAILURE')}
    categories={};timeline={}
    for e in events:
        day=time.strftime('%Y-%m-%d',time.gmtime(e['timestamp']))
        timeline[day]=timeline.get(day,0)+1
        for c in e.get('categories',[]):categories[c]=categories.get(c,0)+1
    page=max(0,int(filters.get('page',0)));size=25
    return dict(events=events[page*size:(page+1)*size],total=len(events),counts=counts,categories=categories,timeline=timeline)