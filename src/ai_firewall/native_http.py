"""Native text lifecycle routes using upstream authentication and permissions.

Registration does not open the outer native runtime allowlist.
"""
import os
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from open_webui.internal.db import AsyncSessionLocal
from open_webui.models.chats import Chats, ChatForm
from open_webui.utils.auth import get_verified_user
from open_webui.utils.firewall import inspector, valid_id

from ai_firewall.native_client import revision
from ai_firewall.native_lifecycle import append_message, complete_chat

router = APIRouter()


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
    if body.chat_id:
        valid_id(body.chat_id)
        await Chats.require_chat_creation_permission(user.id)
        state = await append_message(AsyncSessionLocal, check, user.id, body.chat_id,
            body.revision, body.message_id, body.parent_id, body.content)
    else:
        if body.parent_id is not None:
            raise HTTPException(400, 'native_new_chat_scope_invalid')
        cid = str(uuid4())
        message = {'id': body.message_id, 'parentId': None, 'childrenIds': [],
                   'role': 'user', 'content': body.content, 'models': ['mock']}
        state = await Chats.insert_new_chat(cid, user.id, ChatForm(chat={
            'title': 'New Chat', 'models': ['mock'],
            'history': {'messages': {body.message_id: message}, 'currentId': body.message_id},
        }))
    try:
        state = await complete_chat(AsyncSessionLocal, check, user.id, state.id,
            revision(state.chat), os.environ['NATIVE_LLM_URL'], os.environ['LITELLM_KEY'])
        error = None
    except HTTPException as exception:
        # Clean input is committed. Return only this known canonical snapshot,
        # never provider bodies or unchecked output, so UI can recover/reload.
        error = exception.detail
    return {'chat': state.model_dump(), 'revision': revision(state.chat), 'error': error}