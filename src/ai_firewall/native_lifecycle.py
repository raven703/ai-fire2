"""Locked native text append; deliberately not exposed as an HTTP endpoint."""
from copy import deepcopy
import time
import os
from uuid import UUID
import httpx

from fastapi import HTTPException
from sqlalchemy import text

from ai_firewall.native_client import revision
from ai_firewall.native_writer import inspected_flush


async def append_message(sessions, inspector, user, chat_id, expected_revision,
                         message_id, parent_id, content, *, role='user'):
    """Atomically append both native representations after mandatory DLP.

    Only server code may select assistant role. Caller must never map a client
    role flag to this parameter. No events are emitted before commit.
    """
    from open_webui.models.chats import Chat, ChatModel
    from open_webui.models.chat_messages import ChatMessages, ChatMessage

    for value in (user, chat_id, message_id):
        try:
            if str(UUID(value)) != value:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, 'native_invalid_id') from None
    if role not in {'user', 'assistant'} or not isinstance(content, str):
        raise HTTPException(400, 'native_text_only')
    async with sessions() as session:
        try:
            if session.bind.dialect.name != 'sqlite':
                raise HTTPException(503, 'native_writer_dialect_unsupported')
            await session.execute(text('BEGIN IMMEDIATE'))
            row = await session.get(Chat, chat_id)
            if row is None or row.user_id != user:
                raise HTTPException(404, 'native_chat_not_found')
            current = revision(row.chat)
            if expected_revision != current:
                raise HTTPException(409, 'native_revision_conflict')
            document = deepcopy(row.chat)
            history = document.get('history', {})
            messages = history.get('messages', {})
            if message_id in messages:
                raise HTTPException(409, 'native_message_replayed')
            if parent_id != history.get('currentId') or parent_id not in messages:
                raise HTTPException(409, 'native_parent_conflict')
            if messages[parent_id].get('role') == role:
                raise HTTPException(409, 'native_role_conflict')
            parent_row = await session.get(ChatMessage, f'{chat_id}-{parent_id}')
            if (parent_row is None or parent_row.user_id != user
                    or parent_row.content != messages[parent_id].get('content')):
                raise HTTPException(409, 'native_history_mirror_conflict')
            clean = await inspector.inspect({'content': content}, user, chat_id,
                                            'input' if role == 'user' else 'output', current)
            now = int(time.time())
            message = {'id': message_id, 'parentId': parent_id, 'childrenIds': [],
                       'dlp_policy_revision':getattr(inspector,'policy_revision',None),
                       'role': role, 'content': clean['content'], 'timestamp': now,
                       'done': True}
            messages[parent_id]['childrenIds'] = [message_id]
            messages[message_id] = message
            history['currentId'] = message_id
            history['messages'] = messages
            document['history'] = history
            # Reject divergent legacy mirrors instead of keeping stale content.
            document.pop('messages', None)
            row.chat = document
            row.current_message_id = message_id
            row.updated_at = now
            session.add(ChatMessages._build_message(
                f'{chat_id}-{message_id}', chat_id, user, message, now))
            await inspected_flush(session, inspector, user, chat_id, current)
            await session.commit()
            return ChatModel.model_validate(row)
        except Exception:
            await session.rollback()
            raise


async def complete_chat(sessions, inspector, user, chat_id, expected_revision,
                        llm_url, llm_key, *, debug=None):
    """Nonstream completion from committed history, checked before any write.

    LLM failure leaves the already-committed clean input intact. A concurrent
    append invalidates the output revision; no unchecked output is published.
    """
    from uuid import uuid4
    from open_webui.models.chats import Chat

    async with sessions() as session:
        row = await session.get(Chat, chat_id)
        if row is None or row.user_id != user:
            raise HTTPException(404, 'native_chat_not_found')
        document = deepcopy(row.chat)
    if revision(document) != expected_revision:
        raise HTTPException(409, 'native_revision_conflict')
    history = document['history']
    parent = history['currentId']
    messages = history['messages']
    chain, seen, cursor = [], set(), parent
    while cursor is not None:
        if cursor in seen or cursor not in messages or len(chain) >= 80:
            raise HTTPException(409, 'native_invalid_history')
        seen.add(cursor)
        item = messages[cursor]
        if item.get('role') not in {'user', 'assistant'} or not isinstance(item.get('content'), str):
            raise HTTPException(409, 'native_invalid_history')
        chain.append({'role': item['role'], 'content': item['content']})
        cursor = item.get('parentId')
    chain.reverse()
    if chain[-1]['role'] != 'user':
        raise HTTPException(409, 'native_user_turn_required')
    fields = {str(i): item['content'] for i, item in enumerate(chain)}
    clean = await inspector.inspect(fields, user, chat_id, 'model-request', expected_revision)
    chain = [{'role': item['role'], 'content': clean[str(i)]} for i, item in enumerate(chain)]
    from ai_firewall.native_client import review_execution
    approved=review_execution.get()
    if approved is not None:
        if approved['turn']['message_id']!=parent:raise HTTPException(409,'review_message_mismatch')
        chain[-1]['content']=await inspector.review_model(approved,user,chat_id)
    try:
        async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
            response = await client.post(llm_url + '/v1/chat/completions',
                headers={'Authorization': 'Bearer ' + llm_key},
                json={'model': 'mock', 'stream': False, 'messages': chain})
        response.raise_for_status()
        choices = response.json()['choices']
        if len(choices) != 1:
            raise ValueError()
        message = choices[0]['message']
        if message.get('role') != 'assistant' or message.get('tool_calls') or not isinstance(message.get('content'), str):
            raise ValueError()
        content = message['content']
        if debug is not None and os.getenv('DLP_DEBUG_TEST_ONLY') == 'true':
            # Even a discarded provider output must pass mandatory output DLP.
            checked = await inspector.inspect({'content': content}, user, chat_id, 'output', expected_revision)
            content = checked['content']
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                mode = await client.get(os.environ['NATIVE_MOCK_TEST_URL'] + '/test/scenario',
                    headers={'Authorization': 'Bearer ' + os.environ['TEST_KEY']})
                mode.raise_for_status()
            if mode.json()['scenario'] == 'dlp-debug':
                action = debug['action']
                categories = debug.get('categories', [])
                content = ('Получен запрос: «' + chain[-1]['content'] + '».\n'
                    'Результат DLP: ' + action + '.\n'
                    + ('ПДн обнаружены: ДА.\n' if action == 'MASK' else 'Детекторы ПДн: совпадений не найдено.\n')
                    + 'Категории: ' + (', '.join(categories) or 'нет') + '.\n'
                    'Передано модели: ' + ('только замаскированное сообщение; исходные значения — нет.'
                        if action == 'MASK' else 'проверенное сообщение.'))
    except HTTPException:
        raise
    except Exception:
        # Never propagate provider response bodies or payload-bearing exceptions.
        raise HTTPException(503, 'native_model_failed') from None
    return await append_message(sessions, inspector, user, chat_id, expected_revision,
                                str(uuid4()), parent, content, role='assistant')