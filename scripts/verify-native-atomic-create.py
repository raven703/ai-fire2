"""Real insert_new_chat + ChatMessage + live Gateway on disposable SQLite."""
import asyncio
from contextlib import asynccontextmanager
import os
import sqlite3
import tempfile
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from fastapi import HTTPException

import open_webui.models.chats as models
from open_webui.models.chat_messages import ChatMessage
from ai_firewall.native_permit import initialize
from ai_firewall.native_writer import install
from ai_firewall.native_client import NativeInspector, revision


async def main():
    os.environ['FIREWALL_NATIVE_WRITERS'] = 'true'
    inspector = NativeInspector(os.environ['NATIVE_GATEWAY_URL'], os.environ['NATIVE_GATEWAY_KEY'],
                                os.environ['ADMISSION_KEY'])
    # Avoid unrelated inference/retrieval imports; inject only the production
    # inspector factory, not a fake detector or fake HTTP transport.
    import sys, types
    sys.modules['open_webui.utils.firewall'] = types.SimpleNamespace(inspector=lambda: inspector)
    with tempfile.TemporaryDirectory() as directory:
        path = directory + '/atomic.db'
        engine = create_async_engine('sqlite+aiosqlite:///' + path)
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: models.Chat.__table__.create(sync))
            await connection.run_sync(lambda sync: ChatMessage.__table__.create(sync))
        db = sqlite3.connect(path)
        initialize(db)
        db.commit()
        db.close()
        sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

        @asynccontextmanager
        async def context(db=None):
            async with sessions() as session:
                await session.execute(text('BEGIN IMMEDIATE'))
                yield session

        models.get_async_db_context = context
        async def permission(*args, **kwargs):
            return
        models.Chats.require_chat_creation_permission = permission
        install()
        uid, cid, mid = [str(uuid.uuid4()) for _ in range(3)]
        raw = 'Hello SYNTHETIC_PII_ATOMIC_CREATE'
        def form(value):
            return models.ChatForm(chat={'title': 'New Chat', 'history': {'currentId': mid,
                'messages': {mid: {'id': mid, 'role': 'user', 'content': value, 'timestamp': 1}}}})
        result = await models.Chats.insert_new_chat(cid, uid, form(raw))
        assert result.id == cid
        assert raw not in str(result.chat)
        db = sqlite3.connect(path)
        assert db.execute('SELECT count(*) FROM chat').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM chat_message').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM firewall_nonce').fetchone()[0] == 1
        assert raw not in '\n'.join(db.iterdump())
        db.close()
        try:
            await models.Chats.insert_new_chat(cid, str(uuid.uuid4()), form('safe duplicate'))
            raise AssertionError('existing chat overwritten by another user')
        except HTTPException as error:
            assert error.status_code == 409
        try:
            await models.Chats.insert_new_chat(str(uuid.uuid4()), uid, form('SYNTHETIC_BLOCK_ATOMIC'))
            raise AssertionError('BLOCK persisted')
        except HTTPException:
            pass
        # A real transport outage must leave neither parent nor message rows.
        os.environ['NATIVE_GATEWAY_URL'] = 'http://127.0.0.1:9'
        broken = NativeInspector('http://127.0.0.1:9', os.environ['NATIVE_GATEWAY_KEY'],
                                 os.environ['ADMISSION_KEY'])
        sys.modules['open_webui.utils.firewall'].inspector = lambda: broken
        try:
            await models.Chats.insert_new_chat(str(uuid.uuid4()), uid, form('safe outage input'))
            raise AssertionError('Gateway outage persisted')
        except HTTPException as error:
            assert error.status_code == 503
        db = sqlite3.connect(path)
        assert db.execute('SELECT count(*) FROM chat').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM chat_message').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM firewall_nonce').fetchone()[0] == 1
        db.close()
        await engine.dispose()
        print('PASS real insert_new_chat + ChatMessage: live MASK, atomic commit, BLOCK/outage rollback, duplicate isolation, DB sweep')


asyncio.run(main())