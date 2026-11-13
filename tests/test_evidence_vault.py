import base64
import json
import pytest
from ai_firewall import evidence_vault as vault
from ai_firewall import dlp_events as events

@pytest.fixture
def bao():
    keys={}
    def call(path,data):
        if path.startswith('encrypt'):
            identifier=str(len(keys));keys[identifier]=(data['plaintext'],data['associated_data'])
            return {'ciphertext':identifier}
        value,aad=keys[data['ciphertext']]
        if aad!=data['associated_data']:raise ValueError()
        return {'plaintext':value}
    call.keys=keys
    return call

def context():return dict(event_id='event',user_id='user',chat_id='chat',policy_revision='revision',extension='pdf')

def test_envelope_unique_keys_tamper_and_no_plaintext(tmp_path,monkeypatch,bao):
    monkeypatch.setenv('EVIDENCE_ROOT',str(tmp_path))
    raw=b'%PDF synthetic secret only'
    limits=dict(events.DEFAULTS)
    one=vault.store(raw,context(),limits,bao);two=vault.store(raw,context(),limits,bao)
    assert len({v[0] for v in bao.keys.values()})==2
    assert all(len(base64.b64decode(v[0]))==32 for v in bao.keys.values())
    assert vault.retrieve(one['id'],'event','officer',bao)[0]==raw
    assert raw not in (tmp_path/'ciphertext.db').read_bytes()
    with pytest.raises(ValueError):vault.retrieve(one['id'],'wrong-event','officer',bao)
    with vault.database() as db:
        db.execute('UPDATE objects SET ciphertext=? WHERE id=?',(b'corrupt',one['id']))
        metadata=json.loads(db.execute('SELECT metadata FROM objects WHERE id=?',(two['id'],)).fetchone()[0])
        metadata['user_id']='other'
        db.execute('UPDATE objects SET metadata=? WHERE id=?',(json.dumps(metadata),two['id']))
    for obj in (one,two):
        with pytest.raises(ValueError):vault.retrieve(obj['id'],'event','officer',bao)

def test_ttl_quota_and_audit(tmp_path,monkeypatch,bao):
    monkeypatch.setenv('EVIDENCE_ROOT',str(tmp_path))
    limits=dict(events.DEFAULTS)
    obj=vault.store(b'example',context(),limits,bao)
    with vault.database() as db:
        metadata=json.loads(db.execute('SELECT metadata FROM objects').fetchone()[0]);metadata['expires']=0
        db.execute('UPDATE objects SET metadata=?',(json.dumps(metadata),))
    with pytest.raises(ValueError):vault.retrieve(obj['id'],'event','officer',bao)
    with vault.database() as db:
        assert db.execute('SELECT COUNT(*) FROM objects').fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM audit WHERE operation='TTL_DELETE'").fetchone()[0]==1
    limits['quota_bytes']=1
    with pytest.raises(ValueError):vault.store(b'example',context(),limits,bao)

def test_events_filters_permissions_and_safe_defaults(tmp_path,monkeypatch):
    monkeypatch.setenv('DLP_EVENTS_DB',str(tmp_path/'events.db'))
    assert not events.settings()['enabled']
    assert not events.can_view('admin')
    event=events.create(user_id='user',source='PDF',action='BLOCK',reason_code='POLICY_BLOCK')
    assert events.get(event['event_id'])['evidence']['status']=='DISABLED'
    assert events.query({'action':'BLOCK'})['total']==1
    assert events.query({'source':'CHAT'})['total']==0