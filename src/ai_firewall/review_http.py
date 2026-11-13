"""Owner-confirmed REVIEW continuation; originals never enter history."""
import json
import os
import httpx
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,ConfigDict
from open_webui.utils.auth import get_verified_user
from ai_firewall import dlp_events as events,review_store as store
from ai_firewall.dlp_status_http import vault,retain

router=APIRouter()


async def policy(user):
    async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
        r=await client.post(os.environ['DLP_POLICY_URL']+'/policy-manager',headers={'Authorization':'Bearer '+os.environ['NATIVE_GATEWAY_KEY']},json={'action':'view','actor':user})
    if r.status_code!=200:raise HTTPException(503,'policy_unavailable')
    return r.json()['active']


async def read(review,actor):
    r=await vault('read',json={'id':review['evidence'],'event_id':review['id'],'actor':actor})
    if r.status_code!=200:raise HTTPException(409,'review_evidence_unavailable')
    return store.validate(review,r.content)


async def capture(body,user,event):
    event.update(extension='json',request_kind='MODEL_TURN')
    saved=dict(tenant='synthetic',user=user.id,chat=event['chat_id'],policy=event['policy_revision'],event=event['event_id'],turn=body.model_dump())
    raw=json.dumps(saved,sort_keys=True,separators=(',',':')).encode()
    await retain(event,raw)
    store.register(event,raw)
    return {'review':store.public(store.get(event['event_id'])),'message':'Запрос ожидает согласования сотрудником ИБ','event_id':event['event_id']}


class Decision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    action:str
    reason:str=Field(min_length=1,max_length=1000)


@router.post('/api/v1/dlp/status/{identifier}/decision')
async def decide(identifier:str,body:Decision,user=Depends(get_verified_user)):
    if not store.permitted(user.id):
        events.audit(user.id,identifier,'REVIEW_DECIDE','DENIED')
        raise HTTPException(403,'DLP_REVIEW_DECIDE_required')
    if body.action not in {'APPROVED','REJECTED'} or not body.reason.strip():raise HTTPException(400,'review_decision_invalid')
    review=store.get(identifier);event=events.get(identifier)
    if not review or not event or event['action']!='REVIEW':raise HTTPException(409,'review_unavailable')
    if body.action=='APPROVED':
        if not events.can_view(user.id):raise HTTPException(403,'DLP_EVIDENCE_VIEW_required')
        saved=await read(review,user.id)
        if saved['turn']['file_ids']:raise HTTPException(409,'review_attachment_context_unavailable')
        if await policy(user.id)!=review['policy']:raise HTTPException(409,'review_policy_changed')
    if review['state']==body.action:return {'review':store.public(review)}
    store.move(identifier,'PENDING',body.action,user.id,body.reason.strip())
    return {'review':store.public(store.get(identifier))}


@router.get('/api/v1/dlp/reviews/mine')
async def mine(user=Depends(get_verified_user)):
    with events.database() as db:
        store.init(db)
        ids=[r[0] for r in db.execute('SELECT id FROM reviews WHERE user=? ORDER BY rowid DESC LIMIT 20',(user.id,))]
    return {'reviews':[{k:r[k] for k in ('id','state')} for r in map(store.get,ids)]}


@router.post('/api/v1/dlp/reviews/{identifier}/resume')
async def resume(identifier:str,user=Depends(get_verified_user)):
    review=store.get(identifier)
    if not review or review['user']!=user.id:raise HTTPException(404,'review_not_found')
    if review['state']!='APPROVED':raise HTTPException(409,'review_not_approved')
    saved=await read(review,user.id)
    if await policy(user.id)!=review['policy']:raise HTTPException(409,'review_policy_changed')
    from ai_firewall.native_http import Turn,turn
    from ai_firewall.native_client import review_execution
    if saved['turn']['file_ids']:raise HTTPException(409,'review_attachment_context_unavailable')
    store.move(identifier,'APPROVED','CONSUMED',user.id)
    handle=review_execution.set(saved)
    try:
        body=Turn(**saved['turn']);body.content='[Содержимое скрыто после согласования ИБ]'
        result=await turn(body,user)
        if result.get('error'):raise HTTPException(503,'review_output_refused')
        event=events.get(identifier);event['mock_result']='COMPLETED';events.put(event)
        return result
    except Exception:
        store.move(identifier,'CONSUMED','FAILED',user.id)
        raise HTTPException(503,'review_continuation_failed') from None
    finally:review_execution.reset(handle)