"""Upstream-authenticated status and independently authorized evidence access."""
import json
import os
from pathlib import Path
import time

import httpx
from fastapi import APIRouter,Depends,HTTPException,Request
from starlette.responses import Response
from open_webui.utils.auth import get_verified_user
from ai_firewall import dlp_events as events

router=APIRouter()

def authorize(user):
    if user.role!='admin' and user.id not in os.getenv('DLP_AUDITOR_IDS','').split(','):
        raise HTTPException(403,'dlp_role_required')

async def vault(path,**kwargs):
    write=path in {'store','cleanup'}
    key=Path(os.environ['VAULT_V2_WRITE_KEY_FILE' if write else 'VAULT_V2_REVEAL_KEY_FILE']).read_text().strip()
    async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
        return await client.post(os.environ['VAULT_V2_URL']+'/evidence/'+path,
            headers={'Authorization':'Bearer '+key,**kwargs.pop('headers',{})},**kwargs)

async def retain(event,raw):
    config=events.settings()
    selected={'BLOCK':'store_block','REVIEW':'store_review','TECHNICAL_FAILURE':'store_technical'}.get(event['action'])
    if not config['enabled'] or not selected or not config[selected]:return
    # Commit pending reference first. A crash must never look like a stored object.
    event['evidence']={'status':'PENDING'};events.put(event)
    try:
        response=await vault('store',content=raw,headers={
            'X-Evidence-Context':json.dumps({k:event.get(k) for k in ('event_id','user_id','chat_id','policy_revision','extension')}),
            'X-Evidence-Limits':json.dumps(config)})
        response.raise_for_status()
        event['evidence']=response.json()
    except Exception:
        event['evidence']={'status':'FAILED','reason_code':'EVIDENCE_UNAVAILABLE'}
    events.put(event)

@router.get('/api/v1/dlp/status')
async def status(request:Request,user=Depends(get_verified_user)):
    authorize(user)
    try:result=events.query(dict(request.query_params))
    except (ValueError,TypeError):raise HTTPException(400,'invalid_filters') from None
    return {**result,'settings':events.settings(),'can_edit':user.role=='admin',
            'can_view_evidence':events.can_view(user.id)}

@router.post('/api/v1/dlp/status/settings')
async def configure(data:dict,user=Depends(get_verified_user)):
    if user.role!='admin':raise HTTPException(403,'dlp_admin_required')
    if set(data)!=set(events.DEFAULTS):raise HTTPException(400,'invalid_settings')
    for key in ('enabled','store_block','store_review','store_technical'):
        if type(data[key]) is not bool:raise HTTPException(400,'invalid_settings')
    for key,low,high in (('retention_days',1,365),('max_bytes',1,10485760),('quota_bytes',1048576,10737418240)):
        if type(data[key]) is not int or not low<=data[key]<=high:raise HTTPException(400,'invalid_settings')
    with events.database() as db:db.execute('INSERT OR REPLACE INTO settings VALUES(1,?)',(json.dumps(data),))
    events.audit(user.id,'settings','RETENTION_UPDATE','SUCCESS')
    return data

@router.get('/api/v1/dlp/status/{identifier}')
async def detail(identifier:str,user=Depends(get_verified_user)):
    authorize(user);event=events.get(identifier)
    if not event:raise HTTPException(404,'event_not_found')
    with events.database() as db:
        rows=db.execute('SELECT timestamp,actor,operation,result FROM audit WHERE object=? ORDER BY timestamp DESC LIMIT 100',
            (event['evidence'].get('id',identifier),)).fetchall()
    return {'event':event,'audit':[dict(zip(('timestamp','actor','operation','result'),r)) for r in rows],
        'can_view_evidence':events.can_view(user.id)}

@router.post('/api/v1/dlp/status/{identifier}/evidence')
async def view(identifier:str,user=Depends(get_verified_user)):
    # Separate permission: being an admin or auditor is not sufficient.
    event=events.get(identifier);evidence=(event or {}).get('evidence',{})
    object_id=evidence.get('id',identifier)
    if not events.can_view(user.id):
        events.audit(user.id,object_id,'VIEW','DENIED')
        raise HTTPException(403,'DLP_EVIDENCE_VIEW_required')
    events.audit(user.id,object_id,'VIEW','ATTEMPT')
    if not event or evidence.get('status')!='STORED':raise HTTPException(404,'evidence_unavailable')
    if evidence.get('expires',0)<=time.time():
        events.audit(user.id,object_id,'VIEW','EXPIRED')
        raise HTTPException(410,'evidence_expired')
    try:
        response=await vault('read',json={'id':object_id,'event_id':identifier,'actor':user.id})
        response.raise_for_status()
        # Controlled attachment only, never execute original PDF/HTML/OOXML in SPA.
        events.audit(user.id,object_id,'VIEW','SUCCESS')
        extension=event['extension'] if event['extension'] in {'pdf','png','jpg','jpeg','tif','tiff','webp','txt','docx','xlsx'} else 'bin'
        return Response(response.content,media_type='application/octet-stream',headers={
            'Cache-Control':'no-store, max-age=0','Pragma':'no-cache','X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"sandbox; default-src 'none'",'Content-Disposition':f'attachment; filename="protected-evidence.{extension}"'})
    except Exception:
        events.audit(user.id,object_id,'VIEW','FAILED')
        raise HTTPException(503,'evidence_unavailable') from None