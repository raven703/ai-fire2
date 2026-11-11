import sqlite3

import pytest
from fastapi import HTTPException

from ai_firewall.admission import Admission
from ai_firewall.native_permit import consume, initialize
from ai_firewall.protocol import canonical


def setup(path):
    db = sqlite3.connect(path)
    initialize(db)
    db.execute('CREATE TABLE IF NOT EXISTS content(value TEXT)')
    db.commit()
    admission = Admission(b'a' * 32, 'synthetic-v2')
    payload = dict(user='native-user', operation='chat-write', revision='0' * 64,
                   fields={'content': '[PII_checked]'})
    token = admission.issue(canonical(payload), payload['user'], payload['operation'])
    return db, admission, payload, token


def write(db, admission, payload, token, rev=None):
    db.execute('BEGIN IMMEDIATE')
    consume(db, admission, token, payload, payload['user'], payload['operation'], rev or payload['revision'])
    db.execute('INSERT INTO content VALUES (?)', (payload['fields']['content'],))


def test_real_sqlite_replay_survives_connection_restart(tmp_path):
    path = tmp_path / 'native.db'
    db, admission, payload, token = setup(path)
    write(db, admission, payload, token)
    db.commit()
    db.close()
    db = sqlite3.connect(path)
    with pytest.raises(HTTPException) as error:
        write(db, admission, payload, token)
    assert error.value.status_code == 409
    db.rollback()
    assert db.execute('SELECT count(*) FROM content').fetchone()[0] == 1
    db.close()


def test_permit_and_content_rollback_together(tmp_path):
    db, admission, payload, token = setup(tmp_path / 'native.db')
    write(db, admission, payload, token)
    db.rollback()
    assert db.execute('SELECT count(*) FROM firewall_nonce').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM content').fetchone()[0] == 0
    write(db, admission, payload, token)
    db.commit()
    db.close()


def test_stale_revision_writes_neither_nonce_nor_content(tmp_path):
    db, admission, payload, token = setup(tmp_path / 'native.db')
    with pytest.raises(HTTPException) as error:
        write(db, admission, payload, token, '1' * 64)
    assert error.value.status_code == 409
    assert db.execute('SELECT count(*) FROM firewall_nonce').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM content').fetchone()[0] == 0
    db.rollback()
    db.close()


def test_requires_writer_transaction(tmp_path):
    db, admission, payload, token = setup(tmp_path / 'native.db')
    with pytest.raises(RuntimeError):
        consume(db, admission, token, payload, payload['user'], 'chat-write', payload['revision'])
    db.close()