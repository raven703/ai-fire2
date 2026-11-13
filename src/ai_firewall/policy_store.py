"""Transactional local policy versions. Audit records contain hashes, not text."""
import hashlib
import json
import sqlite3
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from ai_firewall.pii_policy import YAMLPolicy


def validate(document,trusted_patterns=()):
    import yaml
    if not isinstance(document,dict): raise ValueError('invalid_policy')
    # BoundedRegex enforces a runtime timeout, including trusted baseline patterns.
    for rule in document.get('regex',[]):
        pattern=rule.get('pattern','')
        if not isinstance(pattern,str) or len(pattern)>512 or any(x in pattern for x in ('\\1','\\2')):
            raise ValueError('unbounded_regex_not_permitted')
    with tempfile.NamedTemporaryFile(mode='w',suffix='.yaml') as f:
        yaml.safe_dump(document,f); f.flush(); YAMLPolicy(f.name)
    return document


class PolicyStore:
    def __init__(self,path,baseline):
        self.path=path
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,body TEXT NOT NULL);'
                'CREATE TABLE IF NOT EXISTS state(name TEXT PRIMARY KEY,id TEXT NOT NULL);'
                'CREATE TABLE IF NOT EXISTS audit(at INTEGER,actor TEXT,action TEXT,version TEXT,digest TEXT);')
            if not db.execute("SELECT 1 FROM state WHERE name='active'").fetchone():
                import yaml
                document=yaml.safe_load(Path(baseline).read_text())
                self.save(db,document,'bootstrap','publish')

    def db(self): return sqlite3.connect(self.path,timeout=10)

    def save(self,db,document,actor,action):
        body=json.dumps(document,sort_keys=True,separators=(',',':'))
        identifier=uuid4().hex
        db.execute('INSERT INTO versions VALUES(?,?)',(identifier,body))
        db.execute('INSERT OR REPLACE INTO state VALUES(?,?)',('active' if action=='publish' else 'draft',identifier))
        db.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(int(time.time()),actor,action,identifier,hashlib.sha256(body.encode()).hexdigest()))
        return identifier

    def view(self):
        with self.db() as db:
            active=db.execute("SELECT id FROM state WHERE name='active'").fetchone()[0]
            body=json.loads(db.execute('SELECT body FROM versions WHERE id=?',(active,)).fetchone()[0])
            draft=db.execute("SELECT v.id,v.body FROM state s JOIN versions v ON s.id=v.id WHERE s.name='draft'").fetchone()
            history=[dict(zip(('at','actor','action','version','digest'),r)) for r in db.execute('SELECT * FROM audit ORDER BY rowid DESC LIMIT 100')]
            return {'active':active,'policy':body,'draft':{'id':draft[0],'policy':json.loads(draft[1])} if draft else None,'history':history}

    def snapshot(self,identifier=None):
        with self.db() as db:
            if identifier is None:
                identifier=db.execute("SELECT id FROM state WHERE name='active'").fetchone()[0]
            row=db.execute('SELECT body FROM versions WHERE id=?',(identifier,)).fetchone()
            if not row: raise ValueError('unknown_policy_revision')
            return identifier,json.loads(row[0])

    def draft(self,document,actor):
        validate(document)
        with self.db() as db: return self.save(db,document,actor,'draft')

    def publish(self,identifier,actor,expected):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute("SELECT id FROM state WHERE name='active'").fetchone()[0]
            if current!=expected: raise ValueError('policy_revision_conflict')
            row=db.execute('SELECT body FROM versions WHERE id=?',(identifier,)).fetchone()
            if not row: raise ValueError('unknown_version')
            document=json.loads(row[0])
            # Existing baseline regex is trusted; edited drafts validated earlier.
            return self.save(db,document,actor,'publish')

    def discard(self,identifier,actor,expected):
        """Remove only the working pointer; keep immutable versions and audit."""
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            active=db.execute("SELECT id FROM state WHERE name='active'").fetchone()[0]
            draft=db.execute("SELECT id FROM state WHERE name='draft'").fetchone()
            if active!=expected or not draft or draft[0]!=identifier:
                raise ValueError('policy_revision_conflict')
            body=db.execute('SELECT body FROM versions WHERE id=?',(identifier,)).fetchone()[0]
            db.execute("DELETE FROM state WHERE name='draft'")
            db.execute('INSERT INTO audit VALUES(?,?,?,?,?)',(int(time.time()),actor,'discard',identifier,hashlib.sha256(body.encode()).hexdigest()))