"""Sequential policy UI acceptance using dedicated synthetic identities."""
import json
import uuid
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect


def test_policy_publication_and_roles():
    identities=json.loads(Path('/artifacts/.dlp-test-identities.json').read_text())
    api=httpx.Client(base_url='http://webui:8080',timeout=20)
    admin=identities['admin']
    login=api.post('/api/v1/auths/signin',json={k:admin[k] for k in ('email','password')})
    login.raise_for_status()
    headers={'Authorization':'Bearer '+login.json()['token']}
    initial=api.post('/api/v1/dlp/policies',headers=headers,json={'action':'view'}).json()
    baseline=json.loads(json.dumps(initial['policy']))
    for rule in baseline['rules']:
        if rule['entity']=='APPROVAL_REQUIRED': rule['action']='REVIEW'
    draft=api.post('/api/v1/dlp/policies',headers=headers,json={'action':'draft','policy':baseline}).json()
    api.post('/api/v1/dlp/policies',headers=headers,json={'action':'publish','id':draft['id'],'expected':initial['active']}).raise_for_status()
    initial=api.post('/api/v1/dlp/policies',headers=headers,json={'action':'view'}).json()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        try:
            page=browser.new_context().new_page();page.set_default_timeout(20000)
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(admin['email'])
            page.locator('input[type=password]').first.fill(admin['password'])
            page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=40000)
            modal=page.get_by_role('dialog',name="What's New in Open WebUI")
            if modal.is_visible():
                modal.get_by_role('button',name="Okay, Let's Go!").click()
            page.goto('http://webui:8080/admin/dlp',wait_until='domcontentloaded')
            expect(page.get_by_role('heading',name='Защита данных',exact=True)).to_be_visible()
            expect(page.get_by_label('Action PERSON',exact=True)).to_be_visible()
            modal=page.get_by_role('dialog',name="What's New in Open WebUI")
            if modal.is_visible():
                modal.get_by_role('button',name="Okay, Let's Go!").click()
            page.get_by_label('Action APPROVAL_REQUIRED',exact=True).select_option('BLOCK')
            page.get_by_role('button',name='Сохранить черновик',exact=True).click()
            expect(page.get_by_role('button',name='Опубликовать черновик',exact=True)).to_be_enabled()
            with page.expect_response(lambda r:'/api/v1/dlp/policies' in r.url and r.request.post_data_json.get('action')=='publish') as published:
                page.get_by_role('button',name='Опубликовать черновик',exact=True).click()
            assert published.value.status==200
            print('UI published',flush=True)
            page.context.close()
            page=browser.new_context().new_page();page.set_default_timeout(15000)
            identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(identity['email'])
            page.locator('input[type=password]').first.fill(identity['password'])
            page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
            page.goto('http://webui:8080/',wait_until='domcontentloaded')
            modal=page.get_by_role('dialog',name="What's New in Open WebUI")
            if modal.is_visible(): modal.get_by_role('button',name="Okay, Let's Go!").click()
            expect(page.locator('#chat-input')).to_be_visible()
            page.wait_for_timeout(2000)
            modal=page.get_by_role('dialog',name="What's New in Open WebUI")
            if modal.is_visible(): modal.get_by_role('button',name="Okay, Let's Go!").click()
            page.locator('#chat-input').fill('для внутреннего использования')
            print('before BLOCK submit',flush=True)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=40000) as verdict:
                page.locator('#send-message-button').click()
                print('BLOCK Enter dispatched',flush=True)
            print('BLOCK response',verdict.value.status,flush=True)
            assert verdict.value.status==403
            ordinary=api.post('/api/v1/auths/signin',json=identity).json()
            denied=api.post('/api/chat/completions/native',headers={'Authorization':'Bearer '+ordinary['token']},json={'message_id':str(uuid.uuid4()),'content':'для внутреннего использования'})
            assert denied.status_code==403 and denied.json()['detail']=='BLOCK'
            expect(page.get_by_text('Protected message rejected; no unchecked response published',exact=True)).to_be_visible()
            print('chat BLOCK confirmed',flush=True)
            page.context.close()
            page=browser.new_context().new_page()
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(admin['email'])
            page.locator('input[type=password]').first.fill(admin['password'])
            page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
            page.goto('http://webui:8080/admin/dlp',wait_until='domcontentloaded')
            row=page.locator('div.border-b').filter(has_text=initial['active'])
            with page.expect_response(lambda r:'/api/v1/dlp/policies' in r.url and r.request.post_data_json.get('action')=='publish') as restored:
                page.once('dialog', lambda dialog: dialog.accept())
                row.get_by_role('button',name='Восстановить версию',exact=True).first.click()
            assert restored.value.status==200
            print('UI rollback',flush=True)
            page.context.close()
            page=browser.new_context().new_page();page.set_default_timeout(15000)
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(identity['email'])
            page.locator('input[type=password]').first.fill(identity['password'])
            page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
            page.goto('http://webui:8080/',wait_until='domcontentloaded')
            modal=page.get_by_role('dialog',name="What's New in Open WebUI")
            if modal.is_visible(): modal.get_by_role('button',name="Okay, Let's Go!").click()
            expect(page.locator('#chat-input')).to_be_visible()
            page.wait_for_timeout(2000)
            modal=page.get_by_role('dialog',name="What's New in Open WebUI")
            if modal.is_visible(): modal.get_by_role('button',name="Okay, Let's Go!").click()
            page.locator('#chat-input').fill('для внутреннего использования')
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=40000) as verdict:
                page.locator('#send-message-button').click()
            assert verdict.value.status==403
            denied=api.post('/api/chat/completions/native',headers={'Authorization':'Bearer '+ordinary['token']},json={'message_id':str(uuid.uuid4()),'content':'для внутреннего использования'})
            assert denied.status_code==403 and denied.json()['detail']=='REVIEW'
            print('chat REVIEW restored',flush=True)
            for identity,allowed in [(identities['auditor'],True),(json.loads(Path('/artifacts/.native-staging-identity.json').read_text()),False)]:
                context=browser.new_context(); other=context.new_page()
                other.goto('http://webui:8080/auth',wait_until='domcontentloaded')
                other.locator('input[name=email]').fill(identity['email'])
                other.locator('input[type=password]').first.fill(identity['password'])
                with other.expect_response(lambda r:'/api/v1/auths/signin' in r.url) as auth:
                    other.locator('button[type=submit]').click()
                token=auth.value.json()['token'];h={'Authorization':'Bearer '+token}
                view=api.post('/api/v1/dlp/policies',headers=h,json={'action':'view'})
                assert view.status_code==(200 if allowed else 403)
                assert api.post('/api/v1/dlp/policies',headers=h,json={'action':'draft','policy':initial['policy']}).status_code==403
                other.goto('http://webui:8080/admin/dlp',wait_until='domcontentloaded')
                if allowed:
                    expect(other.get_by_label('Action PERSON',exact=True)).to_be_disabled()
                else:
                    expect(other.get_by_role('heading',name='Защита данных',exact=True)).not_to_be_visible()
                context.close()
        finally:
            current=api.post('/api/v1/dlp/policies',headers=headers,json={'action':'view'}).json()
            api.post('/api/v1/dlp/policies',headers=headers,json={'action':'publish','id':initial['active'],'expected':current['active']}).raise_for_status()
            browser.close()