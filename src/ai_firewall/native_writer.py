"""Fail-closed ORM write boundary for native chat tables.

Install on SQLAlchemy Session (also covers AsyncSession's synchronous delegate).
A permit authorizes exact column snapshots, not a request-wide boolean. Consume
the signed nonce using the writer's own DBAPI transaction before flushing rows.
Only SQLite is supported at this synthetic stage; other dialects deny writes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import sqlite3

from fastapi import HTTPException

from ai_firewall.native_permit import consume

_permit = ContextVar('native_writer_permit', default=None)
TABLES = frozenset({'chat', 'chat_message'})


async def inspected_flush(session, inspector, user, chat, current_revision):
    """Flush real ORM rows using a Gateway-signed exact-row permit.

    Caller must already hold the chat revision lock and have canonicalized every
    input. This last check DENIES residual masking needs rather than silently
    changing ORM state after lifecycle events have been constructed.
    """
    sync = session.sync_session
    rows = [row for row in set(sync.new) | set(sync.dirty) | set(sync.deleted)
            if getattr(getattr(row, '__table__', None), 'name', None) in TABLES]
    # Materialize scalar defaults before hashing: SQLAlchemy otherwise injects
    # them during INSERT, after admission has covered a different column value.
    for row in rows:
        if getattr(row, 'user_id', None) != user:
            raise HTTPException(403, 'native_writer_owner_mismatch')
        scope = row.id if row.__table__.name == 'chat' else row.chat_id
        if scope != chat:
            raise HTTPException(403, 'native_writer_chat_mismatch')
        if row not in sync.new:
            continue
        for column in row.__table__.columns:
            if getattr(row, column.key) is None and column.default is not None:
                if not column.default.is_scalar:
                    raise HTTPException(503, 'native_callable_default_unreviewed')
                setattr(row, column.key, column.default.arg)
    actual = sorted(({'table': row.__table__.name, 'delete': row in sync.deleted,
                      'columns': snapshot(row)} for row in rows),
                    key=lambda row: (row['table'], str(row['columns'].get('id'))))
    if not actual:
        return
    fields = {'rows': json.dumps(actual, sort_keys=True, separators=(',', ':'))}
    result = await inspector.inspect(fields, user, chat, 'chat-write', current_revision, receipt=True)
    if result['payload']['fields'] != fields or result['action'] != 'ALLOW':
        raise HTTPException(403, 'native_writer_not_canonical')
    with authorized_write(inspector.receipts, result['admission'], result['payload'], current_revision):
        await session.flush()


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
            cursor = dbapi.cursor()
            try:
                return cursor.execute(statement, parameters)
            except Exception as error:
                # Async adapters wrap sqlite integrity exceptions; normalize for
                # the common transactional replay consumer.
                if isinstance(error, sqlite3.IntegrityError) or 'IntegrityError' in type(error).__name__:
                    raise sqlite3.IntegrityError('native_nonce_conflict') from None
                raise

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