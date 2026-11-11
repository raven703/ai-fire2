"""Run inside native WebUI image with source bind-mounted. Real models/AsyncSession.

Uses a disposable SQLite database, never the running WebUI database.
"""
import asyncio
import json
import os
import sqlite3
import tempfile
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

from open_webui.models.chats import Chat
from ai_firewall.admission import Admission
from ai_firewall.native_permit import initialize
from ai_firewall.native_writer import install, snapshot, authorized_write, inspected_flush
from ai_firewall.native_client import NativeInspector
import httpx
from ai_firewall.protocol import canonical


async def main():
    with tempfile.TemporaryDirectory() as directory:
        path = directory + '/writer.db'
        engine = create_async_engine('sqlite+aiosqlite:///' + path)
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Chat.__table__.create(sync))
        db = sqlite3.connect(path)
        initialize(db)
        db.commit()
        db.close()
        install()
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        def row():
            return Chat(id=str(uuid.uuid4()), user_id=str(uuid.uuid4()), title='Checked',
                        chat={'history': {'messages': {}}}, created_at=1, updated_at=1)
        async with sessions() as session:
            session.add(row())
            try:
                await session.flush()
                raise AssertionError('unchecked real model flush allowed')
            except HTTPException as error:
                assert error.status_code == 403
            await session.rollback()
        admission = Admission(b'a' * 32, 'synthetic-v2')
        async with sessions() as session:
            item = row()
            session.add(item)
            payload = dict(user=item.user_id, operation='chat-write', revision='0' * 64,
                fields={'rows': json.dumps([{'table': 'chat', 'delete': False,
                    'columns': snapshot(item)}], sort_keys=True, separators=(',', ':'))})
            token = admission.issue(canonical(payload), item.user_id, 'chat-write')
            await session.execute(text('BEGIN IMMEDIATE'))
            with authorized_write(admission, token, payload, '0' * 64):
                await session.flush()
                await session.commit()
        db = sqlite3.connect(path)
        assert db.execute('SELECT count(*) FROM chat').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM firewall_nonce').fetchone()[0] == 1
        db.close()
        # Real AsyncSession flush through authenticated HTTP inspection client.
        # Transport stands in for Gateway here; live Gateway is tested separately.
        def gateway(request):
            payload = json.loads(request.content)
            return httpx.Response(200, json={'payload': payload, 'action': 'ALLOW',
                'admission': admission.issue(canonical(payload), payload['user'], payload['operation'])})
        inspector = NativeInspector('http://gateway', 's' * 32, 'a' * 32,
                                    transport=httpx.MockTransport(gateway))
        async with sessions() as session:
            item = row()
            session.add(item)
            await session.execute(text('BEGIN IMMEDIATE'))
            await inspected_flush(session, inspector, item.user_id, item.id, '0' * 64)
            await session.commit()
        db = sqlite3.connect(path)
        assert db.execute('SELECT count(*) FROM chat').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM firewall_nonce').fetchone()[0] == 2
        db.close()
        await engine.dispose()
        print('PASS actual Open WebUI Chat + AsyncSession: deny raw flush, atomic permitted commit')


asyncio.run(main())