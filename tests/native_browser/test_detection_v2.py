"""Original composer smoke; generated fixture inputs only."""
import json
import os
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect


def test_detection_v2_original_ui():
    rows=[json.loads(x) for x in Path('/artifacts/detection-v2/development.jsonl').read_text().splitlines()]
    samples=[rows[i]['text'] for i in (0,1,2,3,4,5,6,7,8,9,10,11)]
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
        for text in ['обычная проверка']+samples:
            page.goto('http://webui:8080/',wait_until='domcontentloaded')
            composer=page.locator('#chat-input'); expect(composer).to_be_visible(timeout=30000)
            composer.fill(text)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as response:
                composer.press('Enter')
            assert response.value.status==200,response.value.text()
            state=response.value.json(); assert state['error'] is None
            if text!='обычная проверка':
                assert '[V2_' in json.dumps(state)
                expect(page.get_by_role('button',name='Показать оригинал',exact=True).first).to_be_visible()
        for text,verdict in [('api_key=sk-test-'+'x'*32,'BLOCK'),
            ('SYNTHETIC_CORPORATE_SECRET','BLOCK'),('для внутреннего использования','REVIEW')]:
            page.goto('http://webui:8080/',wait_until='domcontentloaded')
            composer=page.locator('#chat-input'); expect(composer).to_be_visible(timeout=30000)
            composer.fill(text)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as response:
                composer.press('Enter')
            assert response.value.status==403
            assert response.value.json()['detail']==verdict
        browser.close()