"""Transactional permit consumption for native SQL writers.

Use the SAME sqlite transaction/connection as the content write. No raw content
is retained. This primitive is not installed into native writers yet.
"""
import json
import sqlite3
import time

from fastapi import HTTPException

from ai_firewall.protocol import canonical


def initialize(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS firewall_nonce '
                       '(nonce TEXT PRIMARY KEY, expires INTEGER NOT NULL)')


def consume(connection, admission, token, payload, user, operation, current_revision):
    if not connection.in_transaction:
        raise RuntimeError('permit consumption requires the content transaction')
    if not admission.verify(token, canonical(payload), user, operation):
        raise HTTPException(403, 'invalid_native_admission')
    if (payload.get('user') != user or payload.get('operation') != operation
            or payload.get('revision') != current_revision):
        raise HTTPException(409, 'native_revision_conflict')
    try:
        claims = json.loads(bytes.fromhex(token.split('.')[0]))
        connection.execute('DELETE FROM firewall_nonce WHERE expires <= ?', (int(time.time()),))
        connection.execute('INSERT INTO firewall_nonce(nonce,expires) VALUES (?,?)',
                           (claims['nonce'], claims['expires']))
    except sqlite3.IntegrityError:
        raise HTTPException(409, 'native_admission_replayed') from None