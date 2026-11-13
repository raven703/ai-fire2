"""Fail-closed ORM write boundary for native chat tables.

Install on SQLAlchemy Session (also covers AsyncSession's synchronous delegate).
A permit authorizes exact column snapshots, not a request-wide boolean. Consume
the signed nonce using the writer's own DBAPI transaction before flushing rows.
Only SQLite is supported at this synthetic stage; other dialects deny writes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import hashlib
import sqlite3

from fastapi import HTTPException

from ai_firewall.native_permit import consume, initialize

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
                      'columns': permit_snapshot(row, row in sync.deleted)} for row in rows),
                    key=lambda row: (row['table'], str(row['columns'].get('id'))))
    if not actual:
        return
    fields = {'rows': json.dumps(actual, sort_keys=True, separators=(',', ':'))}
    if all(row['delete'] for row in actual):
        result = await inspector.deletion(fields,user,chat,current_revision)
    else:
        result = await inspector.inspect(fields, user, chat, 'chat-write', current_revision, receipt=True)
        if result['payload']['fields'] != fields or result['action'] != 'ALLOW':
            raise HTTPException(403, 'native_writer_not_canonical')
    with authorized_write(inspector.receipts, result['admission'], result['payload'], current_revision):
        await session.flush()


def snapshot(row):
    return {column.key: getattr(row, column.key) for column in row.__table__.columns}


def permit_snapshot(row, deleting=False):
    if not deleting:
        return snapshot(row)
    # Exact deletion authorization binds the old row without re-submitting its
    # content to NLP/Vault. Deleting cannot publish or introduce plaintext.
    from ai_firewall.protocol import canonical
    # Integrity metadata goes only to the dedicated deletion permit contract.
    digest = hashlib.sha256(canonical(snapshot(row))).hexdigest()
    return {'id': row.id, 'row_sha256': digest}


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
    if payload.get('operation')=='chat-delete':
        from ai_firewall.delete_contract import validate_delete
        validate_delete(payload)
        if any(row not in session.deleted for row in rows):
            raise HTTPException(403,'delete_permit_cannot_write')
    actual = sorted(({'table': row.__table__.name,
                      'delete': row in session.deleted, 'columns': permit_snapshot(row, row in session.deleted)} for row in rows),
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

    transaction = TransactionConnection()
    # DDL participates in the already-open content transaction. This also
    # provisions a fresh database without a race-prone startup-only check.
    initialize(transaction)
    consume(transaction, permit['admission'], permit['token'], payload,
            payload['user'], payload['operation'], permit['revision'])
    permit['consumed'] = True
    permit['sql_open'] = True


def install():
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    if not event.contains(Session, 'before_flush', guard_flush):
        event.listen(Session, 'before_flush', guard_flush)
    if not event.contains(Session, 'do_orm_execute', guard_bulk):
        event.listen(Session, 'do_orm_execute', guard_bulk)
    if not event.contains(Session, 'after_flush_postexec', finish_flush):
        event.listen(Session, 'after_flush_postexec', finish_flush)


def finish_flush(session, flush_context):
    state = _permit.get()
    if state is not None:
        state['sql_open'] = False
    gate = session.connection().info.get('native_gate')
    if gate is not None:
        gate['allow'] = 0


def sql_allowed():
    state = _permit.get()
    return int(bool(state and state.get('consumed') and state.get('sql_open')))


def register_connection(dbapi, record=None):
    gate = {'allow': 0}
    dbapi.create_function('native_write_allowed', 0, lambda: gate['allow'])
    if record is not None:
        record.info['native_gate'] = gate
    return gate


def sql_gate(connection, cursor, statement, parameters, context, executemany):
    if 'native_gate' not in connection.info:
        connection.info['native_gate'] = register_connection(connection.connection.dbapi_connection)
    connection.info['native_gate']['allow'] = sql_allowed()


async def protect_database(engine):
    """Persistent SQLite triggers deny even raw SQL on unregistered connections.

    The callback is deliberately non-deterministic and evaluated for each row,
    not only when SQL is prepared. Missing callback on a raw connection denies.
    """
    from sqlalchemy import event
    if engine.dialect.name != 'sqlite':
        raise RuntimeError('native_writer_dialect_unsupported')
    sync = engine.sync_engine
    if not event.contains(sync, 'connect', register_connection):
        event.listen(sync, 'connect', register_connection)
        event.listen(sync, 'before_cursor_execute', sql_gate)
    async with engine.begin() as connection:
        def configure(c):
            c.info['native_gate'] = register_connection(c.connection.dbapi_connection)
        await connection.run_sync(configure)
        for table in sorted(TABLES):
            for operation in ('INSERT', 'UPDATE', 'DELETE'):
                await connection.exec_driver_sql(
                    f'CREATE TRIGGER IF NOT EXISTS firewall_{table}_{operation.lower()} '
                    f'BEFORE {operation} ON {table} '
                    "WHEN native_write_allowed() != 1 BEGIN "
                    "SELECT RAISE(ABORT, 'native_sql_writer_denied'); END")


def guard_bulk(state):
    """Bulk ORM DML bypasses flush; never allow it on protected content tables."""
    if not (state.is_insert or state.is_update or state.is_delete):
        return
    table = getattr(state.statement, 'table', None)
    if getattr(table, 'name', None) in TABLES:
        raise HTTPException(403, 'native_bulk_writer_disabled')