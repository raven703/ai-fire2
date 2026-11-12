"""New fictional corpus through original composer; one browser per case."""
import json
import os
from pathlib import Path
import httpx
import pytest
from playwright.sync_api import sync_playwright, expect


@pytest.mark.parametrize('case',range(6))
def test_arbitrary_synthetic_mask(case):
    rows=json.loads(Path('/artifacts/.dlp-new-synthetic.json').read_text())
    value=rows[case]
    content=('ИНН: ' if case==1 else 'СНИЛС: ' if case==2 else '')+value
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    control=httpx.Client(base_url='http://mock:8000',headers={'Authorization':'Bearer '+os.environ['TEST_KEY']},timeout=15)
    control.post('/test/scenario',json={'scenario':'dlp-debug'}).raise_for_status()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        try:
            page=browser.new_page();page.set_default_timeout(15000)
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(identity['email'])
            page.locator('input[type=password]').first.fill(identity['password'])
            page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
            page.locator('#chat-input').fill(content)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=60000) as response:
                page.locator('#send-message-button').click()
            assert response.value.status==200
            state=response.value.json();assert state['error'] is None
            masked=json.dumps(state,ensure_ascii=False)
            assert '[V2_' in masked and value not in masked
            assert value not in json.dumps(control.get('/test/last').json(),ensure_ascii=False)
            if case==5:
                for original in rows[:4]:
                    assert original not in masked
                    assert original not in json.dumps(control.get('/test/last').json(),ensure_ascii=False)
            page.get_by_role('button',name='Показать оригинал',exact=True).first.click()
            expect(page.get_by_test_id('revealed-original')).to_be_visible()
            revealed=page.get_by_test_id('revealed-original').inner_text()
            assert value in revealed
            page.locator('#chat-input').fill('Продолжим разговор')
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=60000) as continued:
                page.locator('#send-message-button').click()
            assert continued.value.status==200 and continued.value.json()['error'] is None
            assert value not in json.dumps(control.get('/test/last').json(),ensure_ascii=False)
            page.reload(wait_until='domcontentloaded')
            expect(page.locator('#chat-input')).to_be_visible()
            expect(page.get_by_test_id('revealed-original')).to_have_count(0)
        finally:
            browser.close()