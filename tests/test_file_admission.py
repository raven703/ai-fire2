import sqlite3
import time
import pytest
from fastapi import HTTPException
pytest.importorskip("cryptography")
from ai_firewall import file_admission as admission


def test_encrypted_context_scope_expiry_and_policy(tmp_path,monkeypatch):
    monkeypatch.setenv('ADMISSION_KEY','a'*32)
    real=sqlite3.connect
    path=tmp_path/'files.db'
    monkeypatch.setattr(admission.sqlite3,'connect',lambda *args,**kwargs:real(path))
    fields={'block_0':'Safe [V2_'+'a'*64+']'}
    identifier=admission.save('alice','chat-one','policy-one',fields,[{'page':1}])
    assert admission.load(identifier,'alice','chat-one','policy-one')==fields
    for user,chat,policy in [('bob','chat-one','policy-one'),('alice','chat-two','policy-one'),('alice','chat-one','policy-two')]:
        with pytest.raises(HTTPException):admission.load(identifier,user,chat,policy)
    assert b'Safe' not in path.read_bytes()
    with real(path) as db:db.execute('UPDATE contexts SET expires=?',(int(time.time())-1,))
    with pytest.raises(HTTPException):admission.load(identifier,'alice','chat-one','policy-one')
