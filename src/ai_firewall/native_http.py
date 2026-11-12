"""Native text lifecycle routes using upstream authentication and permissions.

Registration does not open the outer native runtime allowlist.
"""
import os
import re
from pathlib import Path
import httpx
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from open_webui.internal.db import AsyncSessionLocal
from open_webui.models.chats import Chats, ChatForm
from open_webui.utils.auth import get_verified_user
from open_webui.utils.firewall import inspector, valid_id

from ai_firewall.native_client import revision
from ai_firewall.native_lifecycle import append_message, complete_chat
from ai_firewall.native_writer import inspected_flush

router = APIRouter()


class Reveal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message_id: str
    revision: str


@router.post('/api/v1/chats/{chat_id}/native/reveal')
async def reveal_message(chat_id: str, body: Reveal, user=Depends(get_verified_user)):
    valid_id(chat_id); valid_id(body.message_id)
    if not os.getenv('VAULT_V2_URL'): raise HTTPException(503, 'reveal_disabled')
    state = await Chats.get_chat_by_id(chat_id)
    if state is None or state.user_id != user.id: raise HTTPException(404, 'native_chat_not_found')
    if revision(state.chat) != body.revision: raise HTTPException(409, 'native_revision_conflict')
    message = state.chat.get('history', {}).get('messages', {}).get(body.message_id)
    if message is None: raise HTTPException(404, 'native_message_not_found')
    content = message['content']
    tokens = sorted(set(re.findall(r'\[V2_[a-f0-9]{64}\]', content)))
    if not tokens: raise HTTPException(404, 'no_reveal_tokens')
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.post(os.environ['VAULT_V2_URL'] + '/reveal',
                headers={'Authorization': 'Bearer ' + Path(os.environ['VAULT_V2_REVEAL_KEY_FILE']).read_text().strip()},
                json={'tenant': 'synthetic', 'user': user.id, 'chat': chat_id, 'tokens': tokens})
        if response.status_code == 404: raise HTTPException(404, 'mapping_unavailable')
        response.raise_for_status()
        values = response.json()['values']
        if set(values) != set(tokens): raise ValueError()
        for token in tokens: content = content.replace(token, values[token])
        # No mutation, ORM write, admission or model context from this route.
        return {'content': content}
    except HTTPException: raise
    except Exception: raise HTTPException(503, 'reveal_unavailable') from None


@router.get('/api/v1/chats/{chat_id}')
async def preview_chat(chat_id: str, user=Depends(get_verified_user)):
    valid_id(chat_id)
    state = await Chats.get_chat_by_id(chat_id)
    if state is None or state.user_id != user.id:
        raise HTTPException(404, 'native_chat_not_found')
    return state.model_dump()


@router.delete('/api/v1/chats/{chat_id}')
async def delete_chat(chat_id: str, user=Depends(get_verified_user)):
    from sqlalchemy import select, text
    from open_webui.models.chats import Chat
    from open_webui.models.chat_messages import ChatMessage
    valid_id(chat_id)
    async with AsyncSessionLocal() as session:
        await session.execute(text('BEGIN IMMEDIATE'))
        row = await session.get(Chat, chat_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(404, 'native_chat_not_found')
        current = revision(row.chat)
        messages = (await session.execute(select(ChatMessage).where(ChatMessage.chat_id == chat_id))).scalars().all()
        for message in messages:
            await session.delete(message)
        await session.delete(row)
        await inspected_flush(session, inspector(), user.id, chat_id, current)
        await session.commit()
    return True


@router.get('/api/models/native')
async def models(user=Depends(get_verified_user)):
    return {'data': [{'id': 'mock', 'name': 'Mock LLM', 'object': 'model',
                      'owned_by': 'openai', 'info': {'meta': {'capabilities': {}}}}]}


@router.get('/api/v1/chats/native/list')
async def chat_list(user=Depends(get_verified_user)):
    return await Chats.get_chat_list_by_user_id(user.id)


@router.get('/api/v1/chats/{chat_id}/native')
async def read_chat(chat_id: str, user=Depends(get_verified_user)):
    valid_id(chat_id)
    state = await Chats.get_chat_by_id(chat_id)
    if state is None or state.user_id != user.id:
        raise HTTPException(404, 'native_chat_not_found')
    return {'chat': state.model_dump(), 'revision': revision(state.chat)}


class Turn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chat_id: str | None = None
    revision: str | None = None
    parent_id: str | None = None
    message_id: str
    content: str = Field(min_length=1, max_length=16000)


@router.post('/api/chat/completions/native')
async def turn(body: Turn, user=Depends(get_verified_user)):
    valid_id(body.message_id)
    if os.environ.get('FIREWALL_NATIVE_WRITERS') != 'true':
        raise HTTPException(503, 'native_writer_disabled')
    check = inspector()
    debug = None
    new_chat_id = str(uuid4())
    if os.getenv('DLP_DEBUG_TEST_ONLY') == 'true':
        await Chats.require_chat_creation_permission(user.id)
        # Inspect raw turn before canonical storage discards its detection evidence.
        # The response remains backend-local; no metadata is put into the prompt.
        scope = body.chat_id or new_chat_id
        if body.chat_id:
            valid_id(body.chat_id)
            owned = await Chats.get_chat_by_id(body.chat_id)
            if owned is None or owned.user_id != user.id:
                raise HTTPException(404, 'native_chat_not_found')
        debug = await check.inspect({'content': body.content}, user.id, scope,
            'input', revision({}), receipt=True)
        body.content = debug['payload']['fields']['content']
    if body.chat_id:
        valid_id(body.chat_id)
        await Chats.require_chat_creation_permission(user.id)
        state = await append_message(AsyncSessionLocal, check, user.id, body.chat_id,
            body.revision, body.message_id, body.parent_id, body.content)
    else:
        if body.parent_id is not None:
            raise HTTPException(400, 'native_new_chat_scope_invalid')
        cid = new_chat_id
        message = {'id': body.message_id, 'parentId': None, 'childrenIds': [],
                   'role': 'user', 'content': body.content, 'models': ['mock']}
        state = await Chats.insert_new_chat(cid, user.id, ChatForm(chat={
            'title': 'New Chat', 'models': ['mock'],
            'history': {'messages': {body.message_id: message}, 'currentId': body.message_id},
        }))
    try:
        state = await complete_chat(AsyncSessionLocal, check, user.id, state.id,
            revision(state.chat), os.environ['NATIVE_LLM_URL'], os.environ['LITELLM_KEY'], debug=debug)
        error = None
    except HTTPException as exception:
        # Clean input is committed. Return only this known canonical snapshot,
        # never provider bodies or unchecked output, so UI can recover/reload.
        error = exception.detail
    return {'chat': state.model_dump(), 'revision': revision(state.chat), 'error': error}