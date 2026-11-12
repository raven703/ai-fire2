from ai_firewall.mask_attestation import issue, verify


def test_approval_binds_scope_revision_and_values():
    values=['SYNTHETIC_V2_new_value']
    proof=issue('test-only-key','user','chat','revision',values)
    assert verify('test-only-key',proof,'user','chat','revision',values)
    assert not verify('wrong-key',proof,'user','chat','revision',values)
    assert not verify('test-only-key',proof,'other','chat','revision',values)
    assert not verify('test-only-key',proof,'user','chat','changed',values)
    assert not verify('test-only-key',proof,'user','chat','revision',['changed'])
    proof['expires']=0
    assert not verify('test-only-key',proof,'user','chat','revision',values)