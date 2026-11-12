import pytest
from ai_firewall.policy_store import PolicyStore,validate


def test_draft_publish_rollback_and_conflict(tmp_path):
    import yaml
    baseline=tmp_path/'policy.yaml'
    document={'version':'synthetic-evaluation-v1','rules':[{'entity':'PERSON','action':'MASK','threshold':0.5}],'dictionaries':{},'regex':[]}
    baseline.write_text(yaml.safe_dump(document))
    store=PolicyStore(str(tmp_path/'policy.db'),baseline)
    initial=store.view()
    document['rules'][0]['action']='BLOCK'
    draft=store.draft(document,'admin')
    assert store.view()['policy']['rules'][0]['action']=='MASK'
    active=store.publish(draft,'admin',initial['active'])
    assert store.view()['policy']['rules'][0]['action']=='BLOCK'
    with pytest.raises(ValueError): store.publish(draft,'admin',initial['active'])
    store.publish(initial['active'],'admin',active)
    assert store.view()['policy']['rules'][0]['action']=='MASK'
    assert 'body' not in store.view()['history'][0]


def test_unbounded_regex_denied():
    with pytest.raises(ValueError):
        validate({'regex':[{'pattern':'(a+)+','entity':'PERSON'}]})