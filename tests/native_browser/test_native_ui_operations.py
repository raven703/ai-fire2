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
        assert result['chat']['title']=='[ПДн]'
        item=page.locator(f'[data-sidebar-chat-id="{cid}"]').first
        expect(item).to_be_visible(timeout=15000)
        expect(item.locator('[role="checkbox"]')).to_be_visible()
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
        # New Chat must clear both visible history AND the previous native scope.
        page.locator('#sidebar-new-chat-button').filter(visible=True).first.dispatch_event('click')
        expect(page.locator('#chat-input')).to_be_visible()
        page.locator('#chat-input').fill('тестовое сообщение')
        with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as next_turn:
            page.locator('#chat-input').press('Enter')
        assert next_turn.value.status==200
        assert next_turn.value.json()['error'] is None
        assert next_turn.value.json()['chat']['id']!=cid
        next_chat=next_turn.value.json()['chat']
        assert next_chat['title']=='тестовое сообщение'
        expect(page.locator(f'[data-sidebar-chat-id="{next_chat["id"]}"]').first).to_be_visible(timeout=15000)
        expect(composer).to_have_text('',timeout=15000)
        page.locator('#sidebar-new-chat-button').filter(visible=True).first.dispatch_event('click')
        page.wait_for_url('http://webui:8080/')
        expect(composer).to_have_text('',timeout=15000)
        composer.fill('групповое удаление')
        with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as third_turn:
            composer.press('Enter')
        third_id=third_turn.value.json()['chat']['id']
        page.get_by_role('button',name='Open Sidebar',exact=True).filter(visible=True).first.click()
        for selected_id in (next_chat['id'],third_id):
            page.locator(f'[data-sidebar-chat-id="{selected_id}"] [role="checkbox"]').first.click()
        page.get_by_role('button',name='Delete selected chats',exact=True).click()
        page.get_by_role('dialog').get_by_role('button',name='Delete',exact=True).click()
        for selected_id in (next_chat['id'],third_id):
            expect(page.locator(f'[data-sidebar-chat-id="{selected_id}"]')).to_have_count(0,timeout=15000)
            assert page.request.get('http://webui:8080/api/v1/chats/'+selected_id,headers=headers).status==404
        browser.close()