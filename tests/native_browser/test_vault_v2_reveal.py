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
        browser=pw.chromium.launch(args=['--disable-dev-shm-usage', '--unsafely-treat-insecure-origin-as-secure=http://webui:8080'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.goto('http://localhost:8080/auth')
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
        persisted=page.evaluate('''async () => {
            if (!isSecureContext || !('caches' in globalThis) || !('serviceWorker' in navigator)) {
                throw new Error('Secure-context persistence APIs required');
            }
            const records=[];
            for (const info of await indexedDB.databases()) {
                const db=await new Promise((resolve,reject)=>{
                    const request=indexedDB.open(info.name);
                    request.onsuccess=()=>resolve(request.result);
                    request.onerror=()=>reject(new Error('IndexedDB inventory failed'));
                });
                for (const name of db.objectStoreNames) {
                    records.push(await new Promise((resolve,reject)=>{
                        const request=db.transaction(name).objectStore(name).getAll();
                        request.onsuccess=()=>resolve(request.result);
                        request.onerror=()=>reject(new Error('IndexedDB read failed'));
                    }));
                }
                db.close();
            }
            for (const name of ('caches' in globalThis ? await caches.keys() : [])) {
                const cache=await caches.open(name);
                for (const request of await cache.keys()) {
                    records.push(request.url);
                    records.push(await (await cache.match(request)).text());
                }
            }
            records.push('serviceWorker' in navigator ? (await navigator.serviceWorker.getRegistrations()).map(r=>r.scope) : []);
            return JSON.stringify(records);
        }''')
        assert original not in persisted
        for name in ('webui.db','webui.db-wal','webui.db-shm'):
            path=Path('/webui-data')/name
            if path.exists():
                assert original.encode() not in path.read_bytes()
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