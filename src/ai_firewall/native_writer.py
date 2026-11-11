"""Fail-closed ORM write boundary for native chat tables.

Install on SQLAlchemy Session (also covers AsyncSession's synchronous delegate).
A permit authorizes exact column snapshots, not a request-wide boolean. Consume
the signed nonce using the writer's own DBAPI transaction before flushing rows.
Only SQLite is supported at this synthetic stage; other dialects deny writes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json

from fastapi import HTTPException

from ai_firewall.native_permit import consume

_permit = ContextVar('native_writer_permit', default=None)
TABLES = frozenset({'chat', 'chat_message'})


def snapshot(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


@contextmanager
def authorized_write(admission, token, payload, current_revision):
    """Backend-only, single transaction permit. No browser request flag accepted."""
    state = {'admission': admission, 'token': token, 'payload': payload,
             'revision': current_revision, 'consumed': False}
    handle = _permit.set(state)
    try:
        yield
    finally:
        _permit.reset(handle)


def guard_flush(session, flush_context, instances):
    rows = [row for row in set(session.new) | set(session.dirty) | set(session.deleted)
            if getattr(getattr(row, '__table__', None), 'name', None) in TABLES]
    if not rows:
        return
    permit = _permit.get()
    if permit is None or permit['consumed']:
        raise HTTPException(403, 'native_writer_permit_required')
    payload = permit['payload']
    actual = sorted(({'table': row.__table__.name,
                      'delete': row in session.deleted, 'columns': snapshot(row)} for row in rows),
                    key=lambda row: (row['table'], str(row['columns'].get('id'))))
    # Every free-text column, nested JSON value, title and metadata is covered.
    if payload.get('fields') != {'rows': json.dumps(actual, sort_keys=True, separators=(',', ':'))}:
        raise HTTPException(403, 'native_writer_payload_mismatch')
    connection = session.connection()
    if connection.dialect.name != 'sqlite':
        raise HTTPException(503, 'native_writer_dialect_unsupported')
    raw = connection.connection.driver_connection
    # Async sqlite uses an adapted DBAPI connection; synchronous event handlers
    # must use SQLAlchemy's adapted connection, not the raw aiosqlite object.
    dbapi = connection.connection.dbapi_connection
    if not hasattr(raw, 'in_transaction'):
        raise HTTPException(503, 'native_writer_transaction_unsupported')
    class TransactionConnection:
        in_transaction = raw.in_transaction

        def execute(self, statement, parameters=()):
            return dbapi.execute(statement, parameters)

    consume(TransactionConnection(), permit['admission'], permit['token'], payload,
            payload['user'], payload['operation'], permit['revision'])
    permit['consumed'] = True


def install():
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    if not event.contains(Session, 'before_flush', guard_flush):
        event.listen(Session, 'before_flush', guard_flush)
    if not event.contains(Session, 'do_orm_execute', guard_bulk):
        event.listen(Session, 'do_orm_execute', guard_bulk)


def guard_bulk(state):
    """Bulk ORM DML bypasses flush; never allow it on protected content tables."""
    if not (state.is_insert or state.is_update or state.is_delete):
        return
    table = getattr(state.statement, 'table', None)
    if getattr(table, 'name', None) in TABLES:
        raise HTTPException(403, 'native_bulk_writer_disabled')