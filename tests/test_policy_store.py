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


def test_backreference_regex_denied():
    with pytest.raises(ValueError):
        validate({'regex':[{'pattern':r'(a)\1','entity':'PERSON'}]})


def test_discard_is_scoped_and_keeps_history(tmp_path):
    import yaml
    baseline=tmp_path/'baseline.yaml'
    baseline.write_text(yaml.safe_dump(dict(version='test',rules=[dict(entity='PERSON',action='MASK',threshold=.5)],dictionaries={},regex=[])))
    store=PolicyStore(str(tmp_path/'db'),baseline)
    initial=store.view()
    draft=store.draft(initial['policy'],'admin')
    with pytest.raises(ValueError): store.discard('wrong','admin',initial['active'])
    with pytest.raises(ValueError): store.discard(draft,'admin','stale')
    store.discard(draft,'admin',initial['active'])
    current=store.view()
    assert current['draft'] is None
    assert current['active']==initial['active']
    assert current['history'][0]['action']=='discard'
    assert store.snapshot(draft)[1]==initial['policy']
    with pytest.raises(ValueError): store.discard(draft,'admin',initial['active'])


def test_snapshot_and_baseline_edit(tmp_path):
    from pathlib import Path
    baseline=Path('/app/config/pii-policy-v1.yaml')
    store=PolicyStore(str(tmp_path/'db'),baseline)
    initial,document=store.snapshot()
    document['rules'][0]['action']='BLOCK'
    draft=store.draft(document,'admin')
    store.publish(draft,'admin',initial)
    assert store.snapshot(initial)[1]['rules'][0]['action']=='MASK'
    assert store.snapshot()[1]['rules'][0]['action']=='BLOCK'