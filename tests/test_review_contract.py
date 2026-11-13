import copy
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from ai_firewall import review_store as store,dlp_events as events
from ai_firewall.history_delta import changed_fields
from ai_firewall.review_contract import scope,issue,verify


def test_exact_model_permit_scope():
    claims=scope('event',{'content':'secret'},'user','chat','policy')
    token=issue('k'*32,claims)
    assert verify('k'*32,token,claims)
    for key in ('user','chat','policy','fields_hash','tenant','event'):
        changed={**claims,key:'changed'}
        with pytest.raises(HTTPException):verify('k'*32,token,changed)


def test_history_delta_rejects_edit_delete_and_link_substitution():
    before={'chat':{'history':{'messages':{'one':{'content':'canonical','childrenIds':[]}},'currentId':'one'}}}
    after=copy.deepcopy(before)
    after['chat']['history']['messages']['one']['childrenIds']=['two']
    after['chat']['history']['messages']['two']={'content':'new','parentId':'one','childrenIds':[]}
    result=changed_fields(before,after)
    assert 'one' not in result['chat']['history']['messages']
    for mutation in ('edit','remove','link'):
        bad=copy.deepcopy(after)
        if mutation=='edit':bad['chat']['history']['messages']['one']['content']='injected'
        if mutation=='remove':del bad['chat']['history']['messages']['one']
        if mutation=='link':bad['chat']['history']['messages']['one']['childrenIds']=['other']
        with pytest.raises(HTTPException):changed_fields(before,bad)


def test_review_durable_atomic_claim_and_evidence_digest(tmp_path,monkeypatch):
    monkeypatch.setenv('DLP_EVENTS_DB',str(tmp_path/'events.db'))
    event=events.create(user_id='user',chat_id='chat',action='REVIEW',policy_revision='policy',evidence={'status':'STORED','id':'cipher','expires':9999999999})
    raw=json.dumps(dict(tenant='synthetic',user='user',chat='chat',policy='policy')).encode()
    store.register(event,raw)
    assert store.validate(store.get(event['event_id']),raw)['user']=='user'
    with pytest.raises(HTTPException):store.validate(store.get(event['event_id']),b'corrupt')
    def approve(_):
        try:store.move(event['event_id'],'PENDING','APPROVED','officer','approved');return True
        except HTTPException:return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(approve,range(4)))==1
    store.move(event['event_id'],'APPROVED','CONSUMED','user')
    with pytest.raises(HTTPException):store.move(event['event_id'],'APPROVED','CONSUMED','user')
    assert store.get(event['event_id'])['state']=='CONSUMED'
    assert not store.permitted('admin')
    for action in ('BLOCK','TECHNICAL_FAILURE'):
        event['action']=action
        store.register(event,raw)
