"""Admin discovery and draft deletion, without publishing policy changes."""
import json
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright


def test_admin_users_and_discard():
    identities=json.loads(Path('/artifacts/.dlp-test-identities.json').read_text())
    api=httpx.Client(base_url='http://webui:8080',timeout=30)
    admin=identities['admin']
    auth=api.post('/api/v1/auths/signin',json={k:admin[k] for k in ('email','password')})
    auth.raise_for_status()
    headers={'Authorization':'Bearer '+auth.json()['token']}
    initial=api.post('/api/v1/dlp/policies',headers=headers,json={'action':'view'}).json()
    assert api.get('/api/v1/users/',headers=headers).status_code==200
    assert api.get('/api/v1/groups/',headers=headers).status_code==200
    auditor=identities['auditor']
    other=api.post('/api/v1/auths/signin',json={k:auditor[k] for k in ('email','password')}).json()
    denied={'Authorization':'Bearer '+other['token']}
    assert api.get('/api/v1/users/',headers=denied).status_code in (401,403)
    assert api.post('/api/v1/dlp/policies',headers=denied,json={'action':'discard','id':'invalid','expected':initial['active']}).status_code==403
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        try:
            page=browser.new_page()
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(admin['email'])
            page.locator('input[type=password]').first.fill(admin['password'])
            page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=40000)
            failures=[]
            page.on('response',lambda r:failures.append(r.status) if '/api/v1/users/' in r.url and r.status>=400 else None)
            page.goto('http://webui:8080/admin/users/overview',wait_until='domcontentloaded')
            page.wait_for_timeout(3000)
            assert not failures, failures
            document=json.loads(json.dumps(initial['policy']))
            document['rules'].append(dict(entity='TEST_REMOVABLE',action='BLOCK',threshold=.5))
            document['dictionaries']['TEST_REMOVABLE']=['synthetic removable marker']
            document['regex'].append(dict(entity='TEST_REMOVABLE',pattern='SYNTHETIC_REMOVABLE'))
            api.post('/api/v1/dlp/policies',headers=headers,json={'action':'draft','policy':document}).raise_for_status()
            page.goto('http://webui:8080/admin/dlp',wait_until='domcontentloaded')
            row=page.locator('.rule-row').filter(has_text='TEST_REMOVABLE')
            page.once('dialog',lambda d:d.accept())
            row.get_by_role('button',name='Удалить правило',exact=True).click()
            expect(page.get_by_label('Action TEST_REMOVABLE',exact=True)).to_have_count(0)
            with page.expect_response(lambda r:'/api/v1/dlp/policies' in r.url and r.request.post_data_json.get('action')=='draft') as saved:
                page.get_by_role('button',name='Сохранить черновик',exact=True).click()
            assert saved.value.status==200
            expect(page.get_by_role('button',name='Удалить черновик',exact=True)).to_be_enabled()
            current=api.post('/api/v1/dlp/policies',headers=headers,json={'action':'view'}).json()
            assert 'TEST_REMOVABLE' not in current['draft']['policy']['dictionaries']
            assert not any(r['entity']=='TEST_REMOVABLE' for r in current['draft']['policy']['regex'])
            page.once('dialog',lambda d:d.accept())
            with page.expect_response(lambda r:'/api/v1/dlp/policies' in r.url and r.request.post_data_json.get('action')=='discard') as discarded:
                page.get_by_role('button',name='Удалить черновик',exact=True).click()
            assert discarded.value.status==200
            expect(page.get_by_role('button',name='Удалить черновик',exact=True)).to_have_count(0)
            current=api.post('/api/v1/dlp/policies',headers=headers,json={'action':'view'}).json()
            assert current['draft'] is None and current['active']==initial['active']
        finally:
            if initial['draft']:
                api.post('/api/v1/dlp/policies',headers=headers,json={'action':'draft','policy':initial['draft']['policy']}).raise_for_status()
            browser.close()