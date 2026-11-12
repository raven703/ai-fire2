import hashlib
from types import SimpleNamespace

from ai_firewall.native_writer import permit_snapshot
from ai_firewall.protocol import canonical


def test_delete_permit_binds_exact_row_without_plaintext():
    row=SimpleNamespace(id='one',content='SYNTHETIC_BLOCK_OLD_ROW',
        __table__=SimpleNamespace(columns=[SimpleNamespace(key='id'),SimpleNamespace(key='content')]))
    result=permit_snapshot(row,True)
    assert result=={'id':'one','row_sha256':hashlib.sha256(canonical({'id':'one','content':row.content})).hexdigest()}
    assert row.content not in str(result)
    row.content='changed'
    assert permit_snapshot(row,True)!=result
    assert permit_snapshot(row,False)['content']=='changed'