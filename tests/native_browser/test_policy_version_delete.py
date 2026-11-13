"""Delete only a newly created test revision; never delete existing versions."""
import json
from pathlib import Path
import httpx
from playwright.sync_api import expect, sync_playwright


def test_delete_archived_version_and_collapse_audit():
    identities=json.loads(Path('/artifacts/.dlp-test-identities.json').read_text())
    api=httpx.Client(base_url='http://webui:8080',timeout=30)
    def headers(role):
        identity=identities[role]
        result=api.post('/api/v1/auths/signin',json={k:identity[k] for k in ('email','password')})
        result.raise_for_status()
        return {'Authorization':'Bearer '+result.json()['token']}
    admin=headers('admin');auditor=headers('auditor')
    initial=api.post('/api/v1/dlp/policies',headers=admin,json={'action':'view'}).json()
    revision=None
    try:
        created=api.post('/api/v1/dlp/policies',headers=admin,json={'action':'draft','policy':initial['policy']})
        created.raise_for_status();revision=created.json()['id']
        payload={'action':'delete_version','id':revision,'expected':initial['active']}
        assert api.post('/api/v1/dlp/policies',headers=admin,json=payload).status_code==400
        assert api.post('/api/v1/dlp/policies',headers=admin,json={**payload,'id':initial['active']}).status_code==400
        assert api.post('/api/v1/dlp/policies',headers=auditor,json=payload).status_code==403
        api.post('/api/v1/dlp/policies',headers=admin,json={**payload,'action':'discard'}).raise_for_status()
        with sync_playwright() as p:
            browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
            try:
                page=browser.new_page()
                page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
                page.locator('input[name=email]').fill(identities['admin']['email'])
                page.locator('input[type=password]').first.fill(identities['admin']['password'])
                page.locator('button[type=submit]').click()
                expect(page.locator('#chat-input')).to_be_visible(timeout=40000)
                page.goto('http://webui:8080/admin/dlp',wait_until='domcontentloaded')
                toggle=page.get_by_role('button',name='Показать журнал аудита',exact=True)
                expect(toggle).to_have_attribute('aria-expanded','false')
                expect(page.locator('#dlp-audit-log')).to_have_count(0)
                toggle.click()
                rows=page.locator('.history-row').filter(has_text=revision)
                expect(rows).to_have_count(2)
                page.once('dialog',lambda d:d.dismiss())
                rows.first.get_by_role('button',name='Удалить версию',exact=True).click()
                expect(rows.first.get_by_role('button',name='Восстановить версию')).to_be_enabled()
                page.once('dialog',lambda d:d.accept())
                with page.expect_response(lambda r:'/api/v1/dlp/policies' in r.url and r.request.post_data_json.get('action')=='delete_version') as response:
                    rows.first.get_by_role('button',name='Удалить версию',exact=True).click()
                assert response.value.status==200
                expect(rows).to_have_count(3)
                for row in rows.all():
                    expect(row.get_by_role('button',name='Восстановить версию')).to_be_disabled()
                    expect(row.get_by_role('button',name='Удалить версию',exact=True)).to_be_disabled()
                page.get_by_role('button',name='Скрыть журнал аудита',exact=True).click()
                expect(page.locator('#dlp-audit-log')).to_have_count(0)
            finally:browser.close()
        current=api.post('/api/v1/dlp/policies',headers=admin,json={'action':'view'}).json()
        assert current['active']==initial['active']
        assert len([e for e in current['history'] if e['version']==revision])==3
        assert api.post('/api/v1/dlp/policies',headers=admin,json={'action':'publish','id':revision,'expected':initial['active']}).status_code==400
    finally:
        if initial['draft']:
            api.post('/api/v1/dlp/policies',headers=admin,json={'action':'draft','policy':initial['draft']['policy']}).raise_for_status()