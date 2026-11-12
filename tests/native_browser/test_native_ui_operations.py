"""Native original UI connection status and protected preview/delete contracts."""
import json
import uuid
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def test_native_preview_delete_and_no_socket_warning():
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        sockets=[]
        page.on('request',lambda r:sockets.append(r.url) if '/ws/socket.io' in r.url else None)
        page.goto('http://webui:8080/auth')
        page.locator('input[name="email"]').fill(identity['email'])
        page.locator('input[type="password"]').first.fill(identity['password'])
        page.locator('button[type="submit"]').click()
        composer=page.locator('#chat-input'); expect(composer).to_be_visible(timeout=30000)
        composer.fill('Иванов Иван')
        with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as turn:
            composer.press('Enter')
        assert turn.value.status==200
        result=turn.value.json(); assert result['error'] is None
        cid=result['chat']['id']
        token=page.evaluate('localStorage.token')
        headers={'Authorization':'Bearer '+token}
        preview=page.request.get('http://webui:8080/api/v1/chats/'+cid,headers=headers)
        assert preview.status==200 and preview.json()['id']==cid
        assert 'Иванов Иван' not in preview.text()
        page.wait_for_timeout(6000)
        assert not sockets
        expect(page.get_by_text('Соединение потеряно. Повторное подключение...',exact=False)).to_have_count(0)
        deleted=page.request.delete('http://webui:8080/api/v1/chats/'+cid,headers=headers)
        assert deleted.status==200,deleted.text()
        assert page.request.get('http://webui:8080/api/v1/chats/'+cid,headers=headers).status==404
        browser.close()