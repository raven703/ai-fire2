"""Original composer smoke; generated fixture inputs only."""
import json
import os
from pathlib import Path
import httpx
import pytest
from playwright.sync_api import sync_playwright,expect


@pytest.mark.parametrize('case',range(8))
def test_detection_v2_original_ui(case):
    rows=[json.loads(x) for x in Path('/artifacts/detection-v2/development.jsonl').read_text().splitlines()]
    examples=[('обычная проверка','ALLOW',None),
        (rows[0]['text'],'MASK','PERSON'),(rows[1]['text'],'MASK','RU_INN'),
        (rows[2]['text'],'MASK','RU_SNILS'),(rows[3]['text'],'MASK','PHONE_NUMBER'),
        (rows[11]['text'],'MASK','RU_BANK_ACCOUNT'),
        ('api_key=sk-test-'+'x'*32,'BLOCK',None),
        ('для внутреннего использования','REVIEW',None)]
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    control=httpx.Client(base_url='http://mock:8000',headers={'Authorization':'Bearer '+os.environ['TEST_KEY']})
    control.post('/test/scenario',json={'scenario':'dlp-debug'}).raise_for_status()
    with sync_playwright() as p:
        browser=p.chromium.launch(args=['--disable-dev-shm-usage'])
        page=browser.new_page()
        page.goto('http://webui:8080/auth',wait_until='domcontentloaded')
        page.locator('input[name=email]').fill(identity['email'])
        page.locator('input[type=password]').first.fill(identity['password'])
        page.locator('button[type=submit]').click()
        expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
        text,action,category=examples[case]
        for text in [text] if action in ('ALLOW','MASK') else []:
            composer=page.locator('#chat-input'); expect(composer).to_be_visible(timeout=30000)
            composer.fill(text)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as response:
                composer.press('Enter')
            assert response.value.status==200,response.value.text()
            state=response.value.json(); assert state['error'] is None
            rendered=json.dumps(state,ensure_ascii=False)
            assert 'Результат DLP: '+action in rendered
            if category:
                assert category in rendered
                assert '[V2_' in json.dumps(state)
                page.get_by_role('button',name='Показать оригинал',exact=True).first.click()
                expect(page.get_by_test_id('revealed-original')).to_be_visible()
                original=page.get_by_test_id('revealed-original').inner_text()
                composer.fill('Продолжи проверку')
                with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as continued:
                    composer.press('Enter')
                assert continued.value.status==200,continued.value.text()
                assert original not in json.dumps(control.get('/test/last').json(),ensure_ascii=False)
                page.reload(wait_until='domcontentloaded')
                expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
                expect(page.get_by_test_id('revealed-original')).to_have_count(0)
        for text,verdict in [(text,action)] if action in ('BLOCK','REVIEW') else []:
            composer=page.locator('#chat-input'); expect(composer).to_be_visible(timeout=30000)
            composer.fill(text)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as response:
                composer.press('Enter')
            assert response.value.status==403
            assert response.value.json()['detail']==verdict
        browser.close()