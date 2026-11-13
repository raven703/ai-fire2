"""Original SPA acceptance, synthetic documents only; no real LLM."""
import hashlib
import json
from pathlib import Path
import uuid
import httpx
from playwright.sync_api import sync_playwright,expect

def test_status_evidence_workflow():
    identities=json.loads(Path('/artifacts/.dlp-test-identities.json').read_text())
    api=httpx.Client(base_url='http://webui:8080',timeout=125)
    def login(identity):
        r=api.post('/api/v1/auths/signin',json={k:identity[k] for k in ('email','password')});r.raise_for_status()
        return {'Authorization':'Bearer '+r.json()['token']}
    admin=login(identities['admin']);auditor=login(identities['auditor'])
    ordinary=login(json.loads(Path('/artifacts/.native-staging-identity.json').read_text()))
    state=api.get('/api/v1/dlp/status',headers=admin).json()
    assert state['can_view_evidence']
    config=state['settings'];config['enabled']=True
    api.post('/api/v1/dlp/status/settings',headers=admin,json=config).raise_for_status()
    raw=Path('/artifacts/file-corpus/blocked.pdf').read_bytes()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        try:
            page=browser.new_page();page.set_default_timeout(30000)
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(identities['admin']['email']);page.locator('input[type=password]').first.fill(identities['admin']['password']);page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=40000)
            with page.expect_response(lambda r:'/api/v1/files/native' in r.url,timeout=125000) as upload:
                with page.expect_file_chooser() as chooser:page.get_by_role('button',name='Прикрепить файл · DLP + OCR',exact=True).click()
                chooser.value.set_files('/artifacts/file-corpus/blocked.pdf')
            assert upload.value.status==200
            expect(page.get_by_test_id('native-file-status')).to_contain_text('POLICY_BLOCK')
            expect(page.get_by_test_id('native-file-status')).to_contain_text('Документ не отправлен')
            events=api.get('/api/v1/dlp/status?action=BLOCK&source=PDF',headers=admin).json()['events']
            event=next(e for e in events if e['sha256']==hashlib.sha256(raw).hexdigest())
            assert event['categories'] and event['findings'] and event['policy_revision']
            assert event['evidence']['status']=='STORED',event['evidence']
            identifier=event['event_id']
            for headers in (ordinary,auditor):
                assert api.post('/api/v1/dlp/status/'+identifier+'/evidence',headers=headers).status_code==403
            assert api.get('/api/v1/dlp/status',headers=ordinary).status_code==403
            assert api.get('/api/v1/dlp/status',headers=auditor).status_code==200
            downloaded=api.post('/api/v1/dlp/status/'+identifier+'/evidence',headers=admin)
            assert downloaded.status_code==200 and downloaded.content==raw
            assert 'no-store' in downloaded.headers['cache-control']
            page.goto('http://webui:8080/admin/dlp-status',wait_until='domcontentloaded')
            expect(page.get_by_role('heading',name='DLP Status',exact=True)).to_be_visible()
            page.get_by_label('action',exact=True).fill('BLOCK');page.get_by_label('source',exact=True).fill('PDF');page.get_by_role('button',name='Применить фильтры',exact=True).click()
            page.locator('tbody tr').first.get_by_role('button').click()
            expect(page.get_by_test_id('dlp-event-detail')).to_contain_text('POLICY_BLOCK')
            page.once('dialog',lambda d:d.accept())
            with page.expect_download() as download:page.get_by_role('button',name='Просмотреть оригинал',exact=True).click()
            assert download.value.suggested_filename=='protected-evidence.pdf'
            detail=api.get('/api/v1/dlp/status/'+identifier,headers=admin).json()
            assert any(a['operation']=='VIEW' and a['result']=='SUCCESS' for a in detail['audit'])
            assert any(a['result']=='DENIED' for a in detail['audit'])
            print('PASS original composer BLOCK → status filters → findings → encrypted original → RBAC → audit',flush=True)
        finally:browser.close()