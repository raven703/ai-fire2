"""Trusted diagnostics through the original composer and canonical native writes."""
import json
import os
import sqlite3
import uuid
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright, expect


def test_dlp_debug_native():
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    control=httpx.Client(base_url='http://mock:8000',headers={'Authorization':'Bearer '+os.environ['TEST_KEY']})
    control.post('/test/scenario',json={'scenario':'dlp-debug'}).raise_for_status()
    canary='SYNTHETIC_PII_DEBUG_'+uuid.uuid4().hex
    try:
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
                with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as result:
                    composer.press('Enter')
                return result.value
            result=send('Привет, это проверка.')
            assert result.status==200 and result.json()['error'] is None
            expect(page.get_by_text('Результат DLP: ALLOW.',exact=False).first).to_be_visible()
            result=send('Проверка '+canary)
            assert result.status==200 and result.json()['error'] is None
            assert canary not in json.dumps(result.json())
            expect(page.get_by_text('Результат DLP: MASK.',exact=False).first).to_be_visible()
            expect(page.get_by_text('Категории: SYNTHETIC_PII.',exact=False).first).to_be_visible()
            # Real NLP, fictional fixture. No value from this route enters Vault.
            result=send('Тестовый получатель: Иванов Иван Иванович.')
            assert result.status==200 and result.json()['error'] is None
            expect(page.get_by_text('Категории: PERSON.',exact=False).first).to_be_visible()
            before=control.get('/test/last').json()
            for marker in ('SYNTHETIC_BLOCK_DEBUG','SYNTHETIC_REVIEW_DEBUG'):
                assert send(marker).status==403
                assert control.get('/test/last').json()==before
            assert canary not in json.dumps(before)
            assert 'Иванов Иван Иванович' not in json.dumps(before,ensure_ascii=False)
            storage=page.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})')
            assert canary not in storage
            db=sqlite3.connect('file:/webui-data/webui.db?mode=ro',uri=True)
            assert canary not in '\n'.join(db.iterdump()); db.close()
            for path in Path('/webui-data').glob('webui.db*'):
                assert canary.encode() not in path.read_bytes()
            page.reload(); expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
            page.screenshot(path='/artifacts/pii-dlp-debug.png')
            browser.close()
    finally:
        control.post('/test/scenario',json={'scenario':'normal'}).raise_for_status()


def test_nlp_failure_native():
    if os.getenv('NATIVE_FAULT_MODE')!='nlp-down': pytest.skip('explicit NLP fault required')
    identity=json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    control=httpx.Client(base_url='http://mock:8000',headers={'Authorization':'Bearer '+os.environ['TEST_KEY']})
    before=control.get('/test/last').json()
    canary='SYNTHETIC_PII_NLP_FAILURE_'+uuid.uuid4().hex
    with sync_playwright() as pw:
        browser=pw.chromium.launch(args=['--disable-dev-shm-usage'])
        page=browser.new_page(); page.goto('http://webui:8080/auth')
        page.locator('input[name="email"]').fill(identity['email'])
        page.locator('input[type="password"]').first.fill(identity['password'])
        page.locator('button[type="submit"]').click()
        composer=page.locator('#chat-input'); expect(composer).to_be_visible(timeout=30000)
        composer.fill(canary)
        with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=30000) as response:
            composer.press('Enter')
        assert response.value.status==503
        assert control.get('/test/last').json()==before
        for path in Path('/webui-data').glob('webui.db*'): assert canary.encode() not in path.read_bytes()
        assert canary not in page.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})')
        browser.close()