"""Native text lifecycle routes using upstream authentication and permissions.

Registration does not open the outer native runtime allowlist.
"""
import os
import re
from pathlib import Path
import httpx
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from open_webui.internal.db import AsyncSessionLocal
from open_webui.models.chats import Chats, ChatForm
from open_webui.utils.auth import get_verified_user
from open_webui.utils.firewall import inspector, valid_id

from ai_firewall.native_client import revision
from ai_firewall.native_lifecycle import append_message, complete_chat
from ai_firewall.native_writer import inspected_flush

router = APIRouter()


@router.post('/api/v1/dlp/policies')
async def policy_manager(data:dict,user=Depends(get_verified_user)):
    # Explicit auditor identities are operator configuration, never browser claims.
    auditors=set(os.getenv('DLP_AUDITOR_IDS','').split(','))
    if user.role!='admin' and user.id not in auditors:
        raise HTTPException(403,'dlp_role_required')
    if user.role!='admin' and data.get('action')!='view':
        raise HTTPException(403,'dlp_admin_required')
    if set(data)-{'action','policy','id','ids','expected'}:
        raise HTTPException(400,'invalid_policy_request')
    try:
        async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
            response=await client.post(os.environ['DLP_POLICY_URL']+'/policy-manager',
                headers={'Authorization':'Bearer '+os.environ['NATIVE_GATEWAY_KEY']},
                json={**data,'actor':user.id})
        if response.status_code!=200: raise HTTPException(response.status_code,'policy_operation_denied')
        result=response.json()
        result['can_edit']=user.role=='admin'
        return result
    except httpx.HTTPError: raise HTTPException(503,'policy_service_unavailable') from None


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


@router.post('/api/v1/files/native')
async def file_upload(request:Request,user=Depends(get_verified_user)):
    await Chats.require_chat_creation_permission(user.id)
    if user.role!='admin' and not (getattr(user,'permissions',None) or {}).get('chat',{}).get('file_upload',True):
        raise HTTPException(403,'file_upload_denied')
    chat_id=request.headers.get('X-Chat-ID','');valid_id(chat_id)
    existing=await Chats.get_chat_by_id(chat_id)
    if existing is not None and existing.user_id!=user.id:raise HTTPException(404,'native_chat_not_found')
    extension=request.headers.get('X-File-Extension','')
    # Query policy before extraction so the complete lifecycle pins one revision.
    async with httpx.AsyncClient(timeout=115,trust_env=False) as client:
        policy=await client.post(os.environ['DLP_POLICY_URL']+'/policy-manager',headers={'Authorization':'Bearer '+os.environ['NATIVE_GATEWAY_KEY']},json={'action':'view','actor':user.id})
        if policy.status_code!=200:raise HTTPException(503,'policy_service_unavailable')
        pinned=policy.json()['active']
        result=await client.post(os.environ['NATIVE_FILE_OCR_URL']+'/extract',headers={'Authorization':'Bearer '+os.environ['NATIVE_GATEWAY_KEY'],'X-File-Extension':extension},content=await request.body())
    if result.status_code!=200:return {'action':'REVIEW','categories':[],'reasons':['extraction_unavailable'],'status':'incomplete'}
    extracted=result.json()
    if extracted['status']!='COMPLETE':return {'action':'REVIEW','categories':[],'reasons':extracted['reasons'],'status':'incomplete'}
    blocks=extracted['blocks']
    fields={f'block_{i}':block['text'] for i,block in enumerate(blocks)}
    check=inspector();check.policy_revision=pinned
    try:
        verdict=await check.inspect(fields,user.id,chat_id,'input',revision({}),receipt=True)
    except HTTPException as exc:
        if exc.status_code==403:return {'action':exc.detail if exc.detail in {'BLOCK','REVIEW'} else 'REVIEW','categories':[],'reasons':['policy_denied'],'status':'denied'}
        raise
    from ai_firewall.file_admission import save
    # Never return raw OCR text/word strings or user-controlled filenames.
    metadata=[]
    for i,block in enumerate(blocks):
        source=block['source']
        page_match=re.search(r'(?:page|frame)/(\d+)',source)
        metadata.append({'block':f'block_{i}','page':int(page_match[1]) if page_match else None,
            'part':i+1,'source_type':'sheet' if source.startswith('sheet/') else 'document',
            'method':block.get('method'),'confidence':block.get('confidence'),'variant':block.get('variant'),
            'status':block.get('status'),'boxes':[w['bbox'] for w in block.get('words',[])],
            'word_confidence':[w['confidence'] for w in block.get('words',[])]})
    identifier=save(user.id,chat_id,pinned,verdict['payload']['fields'],metadata)
    return {'id':identifier,'chat_id':chat_id,'action':verdict['action'],'categories':verdict.get('categories',[]),'policy_revision':pinned,'status':'ready','blocks':metadata}


class Turn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chat_id: str | None = None
    revision: str | None = None
    parent_id: str | None = None
    message_id: str
    file_ids: list[str] = Field(default_factory=list,max_length=4)
    new_chat_id: str | None = None
    content: str = Field(min_length=1, max_length=16000)


@router.post('/api/chat/completions/native')
async def turn(body: Turn, user=Depends(get_verified_user)):
    from ai_firewall.native_client import pinned_file_policy
    handle=pinned_file_policy.set(None)
    try:return await file_turn(body,user)
    finally:pinned_file_policy.reset(handle)


async def file_turn(body: Turn,user):
    valid_id(body.message_id)
    if os.environ.get('FIREWALL_NATIVE_WRITERS') != 'true':
        raise HTTPException(503, 'native_writer_disabled')
    check = inspector()
    debug = None
    new_chat_id = body.new_chat_id or str(uuid4())
    valid_id(new_chat_id)
    if body.new_chat_id and await Chats.get_chat_by_id(new_chat_id) is not None:
        raise HTTPException(409,'native_new_chat_scope_conflict')
    if body.chat_id:
        valid_id(body.chat_id)
        owned=await Chats.get_chat_by_id(body.chat_id)
        if owned is None or owned.user_id!=user.id:raise HTTPException(404,'native_chat_not_found')
    if body.file_ids:
        from ai_firewall.file_admission import load
        async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
            response=await client.post(os.environ['DLP_POLICY_URL']+'/policy-manager',headers={'Authorization':'Bearer '+os.environ['NATIVE_GATEWAY_KEY']},json={'action':'view','actor':user.id})
        if response.status_code!=200:raise HTTPException(503,'policy_service_unavailable')
        check.policy_revision=response.json()['active']
        from ai_firewall.native_client import pinned_file_policy
        pinned_file_policy.set(check.policy_revision)
        contexts=[]
        for identifier in body.file_ids:
            valid_id(identifier)
            fields=load(identifier,user.id,body.chat_id or new_chat_id,check.policy_revision)
            contexts.extend(fields.values())
        body.content+='\n\n[Проверенное вложение]\n'+'\n'.join(contexts)
        if len(body.content)>7000:raise HTTPException(413,'file_context_too_large')
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
        # Derive titles only from canonical DLP output, never raw input or reveal.
        clean = await check.inspect({'content': body.content}, user.id, cid,
                                    'input', revision({}))
        body.content = clean['content']
        title = re.sub(r'\[V2_[^\]]+\]', '[ПДн]', body.content)
        title = ' '.join(title.split())[:72] or 'Защищённый чат'
        message = {'id': body.message_id, 'parentId': None, 'childrenIds': [],
                   'dlp_policy_revision':check.policy_revision,
                   'role': 'user', 'content': body.content, 'models': ['mock']}
        state = await Chats.insert_new_chat(cid, user.id, ChatForm(chat={
            'title': title, 'models': ['mock'],
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