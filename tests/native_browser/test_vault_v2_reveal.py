"""Actual original composer + component reveal, token-only model history."""
import json
import os
import sqlite3
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect


def test_vault_v2_reversible_native():
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    original='Иванов Иван'
    control=httpx.Client(base_url='http://mock:8000',headers={'Authorization':'Bearer '+os.environ['TEST_KEY']})
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto('http://webui:8080/auth')
        page.locator('input[name="email"]').fill(identity['email'])
        page.locator('input[type="password"]').first.fill(identity['password'])
        page.locator('button[type="submit"]').click()
        composer=page.locator('#chat-input'); expect(composer).to_be_visible(timeout=30000)
        def send(value):
            composer.fill(value)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as response:
                composer.press('Enter')
            assert response.value.status==200
            data=response.value.json(); assert data['error'] is None
            return data
        state=send('Тестовый получатель: '+original+'.')
        assert original not in json.dumps(state,ensure_ascii=False)
        assert '[V2_' in json.dumps(state)
        cid=state['chat']['id']
        page.get_by_role('button',name='Показать оригинал',exact=True).first.click()
        expect(page.get_by_test_id('revealed-original')).to_contain_text(original)
        send('Продолжи тестовый диалог.')
        capture=control.get('/test/last').json()
        assert original not in json.dumps(capture,ensure_ascii=False)
        assert '[V2_' in json.dumps(capture)
        storage=page.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})')
        assert original not in storage
        db=sqlite3.connect('file:/webui-data/webui.db?mode=ro',uri=True)
        assert original not in '\n'.join(db.iterdump()); db.close()
        page.reload(); expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
        expect(page.get_by_test_id('revealed-original')).to_have_count(0)
        expect(page.get_by_role('button',name='Показать оригинал',exact=True).first).to_be_visible()
        token=page.evaluate('localStorage.token')
        headers={'Authorization':'Bearer '+token}
        history=page.request.get('http://webui:8080/api/v1/chats/'+cid+'/native',headers=headers).json()
        mid=next(k for k,v in history['chat']['chat']['history']['messages'].items() if v['role']=='user')
        stale=page.request.post('http://webui:8080/api/v1/chats/'+cid+'/native/reveal',headers=headers,
            data={'message_id':mid,'revision':'0'*64})
        assert stale.status==409
        page.screenshot(path='/artifacts/vault-v2-reveal-reload.png')
        browser.close()