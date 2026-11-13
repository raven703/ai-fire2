"""Original Open WebUI upload -> OCR -> Vault MASK -> chat -> Mock -> reload."""
import json
import os
from pathlib import Path
import uuid
import httpx
import pytest
from playwright.sync_api import expect,sync_playwright

ROOT=Path('/artifacts/file-corpus')

@pytest.mark.parametrize('filename,category,original',[('scan.pdf','PERSON','Иван Петрович Соколов'),('person.png','PERSON','Иван Петрович Соколов'),('phone.jpg','PHONE_NUMBER','+7 (999) 123-45-67'),('mixed.pdf','RU_SNILS','112-233-445 95')])
def test_file_chat(filename,category,original):
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    control=httpx.Client(base_url='http://mock:8000',headers={'Authorization':'Bearer '+os.environ['TEST_KEY']},timeout=20)
    control.post('/test/scenario',json={'scenario':'dlp-debug'}).raise_for_status()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        try:
            page=browser.new_page();page.set_default_timeout(20000)
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(identity['email'])
            page.locator('input[type=password]').first.fill(identity['password'])
            page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=40000)
            expect(page.get_by_role('button',name='Прикрепить файл · DLP + OCR',exact=True)).to_be_visible()
            with page.expect_response(lambda r:'/api/v1/files/native' in r.url,timeout=125000) as uploaded:
                with page.expect_file_chooser() as chooser:
                    page.get_by_role('button',name='Прикрепить файл · DLP + OCR',exact=True).click()
                chooser.value.set_files(str(ROOT/filename))
            assert uploaded.value.status==200
            expect(page.get_by_test_id('native-file-status')).to_contain_text(category)
            expect(page.get_by_test_id('native-file-status')).to_contain_text('MASK')
            page.locator('#chat-input').fill('Кратко опиши проверенный документ')
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=60000) as sent:
                page.locator('#send-message-button').click()
            assert sent.value.status==200
            result=sent.value.json();assert result['error'] is None
            safe=json.dumps(result,ensure_ascii=False)
            assert original not in safe and '[V2_' in safe
            assert original not in json.dumps(control.get('/test/last').json(),ensure_ascii=False)
            page.locator('#chat-input').fill('Продолжим с безопасным контекстом')
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=60000) as continued:
                page.locator('#send-message-button').click()
            assert continued.value.status==200 and continued.value.json()['error'] is None
            assert original not in json.dumps(control.get('/test/last').json(),ensure_ascii=False)
            page.reload(wait_until='domcontentloaded')
            expect(page.locator('#chat-input')).to_be_visible()
            assert original not in page.locator('body').inner_text()
        finally:browser.close()


def test_incomplete_and_block_upload():
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        try:
            page=browser.new_page()
            page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
            page.locator('input[name=email]').fill(identity['email']);page.locator('input[type=password]').first.fill(identity['password']);page.locator('button[type=submit]').click()
            expect(page.locator('#chat-input')).to_be_visible(timeout=40000)
            for filename,action in [('bad.png','TECHNICAL_FAILURE'),('corrupt.pdf','TECHNICAL_FAILURE'),('secret.txt','BLOCK')]:
                with page.expect_response(lambda r:'/api/v1/files/native' in r.url,timeout=125000) as uploaded:
                    with page.expect_file_chooser() as chooser:
                        page.get_by_role('button',name='Прикрепить файл · DLP + OCR',exact=True).click()
                    chooser.value.set_files(str(ROOT/filename))
                assert uploaded.value.status==200
                expect(page.get_by_test_id('native-file-status')).to_contain_text(action)
                calls=[]
                page.on('request',lambda r:calls.append(r.url) if '/api/chat/completions/native' in r.url else None)
                page.locator('#chat-input').fill('Попробуй прочитать файл')
                page.locator('#send-message-button').click();page.wait_for_timeout(500)
                assert not calls
                page.goto('http://webui:8080/',wait_until='domcontentloaded')
                expect(page.locator('#chat-input')).to_be_visible()
        finally:browser.close()
