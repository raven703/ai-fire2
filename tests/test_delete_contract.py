import json
import uuid
import pytest
from fastapi import HTTPException
from ai_firewall.delete_contract import validate_delete


def manifest():
    chat=str(uuid.uuid4())
    return dict(user=str(uuid.uuid4()),chat=chat,operation='chat-delete',revision='0'*64,
        fields={'rows':json.dumps([{'table':'chat','delete':True,'columns':{'id':chat,'row_sha256':'1'*64}}])})


def test_manifest():
    data=manifest()
    assert validate_delete(data)==data


@pytest.mark.parametrize('change',['update','scope','digest','duplicate','content'])
def test_invalid(change):
    data=manifest();rows=json.loads(data['fields']['rows'])
    if change=='update':rows[0]['delete']=False
    if change=='scope':rows[0]['columns']['id']=str(uuid.uuid4())
    if change=='digest':rows[0]['columns']['row_sha256']='bad'
    if change=='duplicate':rows*=2
    if change=='content':rows[0]['columns']['content']='unchecked'
    data['fields']['rows']=json.dumps(rows)
    with pytest.raises(HTTPException):validate_delete(data)