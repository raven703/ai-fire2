"""Actual SQLAlchemy flushes against SQLite, not API mocks."""
import json

import pytest
from fastapi import HTTPException

from ai_firewall.admission import Admission
from ai_firewall.native_permit import initialize
from ai_firewall.protocol import canonical


def test_real_orm_requires_exact_single_use_permit(tmp_path):
    sqlalchemy = pytest.importorskip('sqlalchemy')
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
    from ai_firewall.native_writer import install, authorized_write, snapshot

    class Base(DeclarativeBase):
        pass

    class Chat(Base):
        __tablename__ = 'chat'
        id: Mapped[str] = mapped_column(primary_key=True)
        content: Mapped[str]

    engine = sqlalchemy.create_engine('sqlite:///' + str(tmp_path / 'orm.db'))
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        initialize(connection.connection.driver_connection)
        connection.commit()
    install()
    admission = Admission(b'a' * 32, 'synthetic-v2')
    with Session(engine) as session:
        row = Chat(id='one', content='checked')
        session.add(row)
        with pytest.raises(HTTPException):
            session.flush()
        session.rollback()
    with Session(engine) as session:
        row = Chat(id='one', content='checked')
        session.add(row)
        payload = {'user': 'native', 'operation': 'chat-write', 'revision': '0' * 64,
                   'fields': {'rows': json.dumps([{'table': 'chat', 'delete': False,
                       'columns': snapshot(row)}], sort_keys=True, separators=(',', ':'))}}
        token = admission.issue(canonical(payload), 'native', 'chat-write')
        # Explicit transaction ensures nonce and content share SQLite transaction.
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        with authorized_write(admission, token, payload, '0' * 64):
            session.flush()
            row.content = 'unchecked mutation'
            with pytest.raises(HTTPException):
                session.flush()
        session.rollback()
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT count(*) FROM chat').scalar() == 0
        assert connection.exec_driver_sql('SELECT count(*) FROM firewall_nonce').scalar() == 0
    with Session(engine) as session:
        with pytest.raises(HTTPException):
            session.execute(sqlalchemy.insert(Chat).values(id='bulk', content='unchecked'))
    # Successful native ORM write consumes a durable nonce in the SAME commit.
    with Session(engine) as session:
        row = Chat(id='committed', content='checked')
        session.add(row)
        payload['fields']['rows'] = json.dumps([{'table': 'chat', 'delete': False,
            'columns': snapshot(row)}], sort_keys=True, separators=(',', ':'))
        token = admission.issue(canonical(payload), 'native', 'chat-write')
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        with authorized_write(admission, token, payload, '0' * 64):
            session.flush()
            session.commit()
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT count(*) FROM chat').scalar() == 1
        assert connection.exec_driver_sql('SELECT count(*) FROM firewall_nonce').scalar() == 1