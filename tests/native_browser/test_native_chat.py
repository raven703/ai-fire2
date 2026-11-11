"""Original native components, real browser, real inference services."""
import json
import sqlite3
from pathlib import Path
import uuid
import os
import httpx

from playwright.sync_api import sync_playwright, expect


def test_native_multiturn():
    identity = json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    canary = 'SYNTHETIC_PII_TEST_' + uuid.uuid4().hex
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        layout_writes = []
        page.on('request', lambda request: layout_writes.append(request.url)
                if request.method == 'POST' and request.url.endswith('/view') else None)
        page.goto('http://webui:8080/auth')
        page.locator('input[name="email"]').fill(identity['email'])
        page.locator('input[type="password"]').first.fill(identity['password'])
        page.locator('button[type="submit"]').click()
        page.wait_for_url('http://webui:8080/', timeout=30000)
        page.screenshot(path='/artifacts/native-chat-before.png')
        composer = page.locator('#chat-input')
        expect(composer).to_be_visible(timeout=30000)
        composer.fill('Hello ' + canary)
        with page.expect_response(lambda r: '/api/chat/completions/native' in r.url, timeout=90000) as turn:
            composer.press('Enter')
        assert turn.value.status == 200, turn.value.text()
        first = turn.value.json()
        assert first['error'] is None, first['error']
        assert canary not in json.dumps(first)
        expect(page.get_by_text('[PII_', exact=False).first).to_be_visible(timeout=10000)
        composer.fill('Continue synthetic conversation')
        with page.expect_response(lambda r: '/api/chat/completions/native' in r.url, timeout=90000) as turn:
            composer.press('Enter')
        assert turn.value.status == 200, turn.value.text()
        second = turn.value.json()
        assert second['error'] is None
        assert len(second['chat']['chat']['history']['messages']) == 4
        page.reload()
        page.wait_for_timeout(3000)
        page.screenshot(path='/artifacts/native-reload-debug.png')
        expect(page.get_by_text('Continue synthetic conversation', exact=False).filter(visible=True).first).to_be_visible(timeout=30000)
        page.screenshot(path='/artifacts/native-chat-history.png')
        expect(page.get_by_text('Layout changes not saved.', exact=False)).to_have_count(0)
        assert layout_writes == [], 'Unchecked layout must remain RAM-only'
        storage = page.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})')
        assert canary not in storage
        composer.fill('SYNTHETIC_BLOCK_BROWSER')
        with page.expect_response(lambda r: '/api/chat/completions/native' in r.url, timeout=30000) as blocked:
            composer.press('Enter')
        assert blocked.value.status == 403
        capture = httpx.get('http://mock:8000/test/last',
            headers={'Authorization': 'Bearer ' + os.environ['TEST_KEY']}).json()
        assert canary not in json.dumps(capture)
        assert len(capture['messages']) == 3
        token = page.evaluate('localStorage.token')
        foreign = page.request.post('http://webui:8080/api/v1/auths/signup', data={
            'name': 'Synthetic Isolation', 'email': 'isolation' + uuid.uuid4().hex + '@synthetic.invalid',
            'password': uuid.uuid4().hex + uuid.uuid4().hex})
        assert foreign.status == 200
        foreign_read = page.request.get('http://webui:8080/api/v1/chats/' + second['chat']['id'] + '/native',
            headers={'Authorization': 'Bearer ' + foreign.json()['token']})
        assert foreign_read.status in (401, 403, 404)
        for path in ['/api/chat/completions', '/api/v1/chats/new',
                     '/api/v1/chats/' + second['chat']['id']]:
            denied = page.request.post('http://webui:8080' + path,
                headers={'Authorization': 'Bearer ' + token}, data={'content': canary})
            assert denied.status == 503
        db = sqlite3.connect('file:/webui-data/webui.db?mode=ro', uri=True)
        assert canary not in '\n'.join(db.iterdump())
        db.close()
        browser.close()


def test_native_model_failure_and_output_block():
    identity = json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    control = httpx.Client(base_url='http://mock:8000',
        headers={'Authorization': 'Bearer ' + os.environ['TEST_KEY']})
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=['--disable-dev-shm-usage'])
            for scenario in ('error', 'injection', 'leak'):
                control.post('/test/scenario', json={'scenario': scenario}).raise_for_status()
                page = browser.new_page()
                page.goto('http://webui:8080/auth')
                page.locator('input[name="email"]').fill(identity['email'])
                page.locator('input[type="password"]').first.fill(identity['password'])
                page.locator('button[type="submit"]').click()
                composer = page.locator('#chat-input')
                expect(composer).to_be_visible(timeout=30000)
                composer.fill('Safe synthetic fault test')
                with page.expect_response(lambda r: '/api/chat/completions/native' in r.url, timeout=90000) as turn:
                    composer.press('Enter')
                assert turn.value.status == 200
                result = turn.value.json()
                messages = result['chat']['chat']['history']['messages']
                assert len(messages) == (2 if scenario == 'leak' else 1)
                assert bool(result['error']) == (scenario != 'leak')
                assert 'SYNTHETIC_PII_OUTPUT_CANARY' not in json.dumps(result)
                assert 'SYNTHETIC_BLOCK_IGNORE_POLICY' not in json.dumps(result)
                page.close()
            browser.close()
    finally:
        control.post('/test/scenario', json={'scenario': 'normal'}).raise_for_status()


def test_gateway_outage_browser():
    """Run separately with native Gateway stopped by the host orchestrator."""
    if os.environ.get('NATIVE_FAULT_MODE') != 'gateway-down':
        import pytest
        pytest.skip('requires explicit Gateway outage')
    identity = json.loads(Path('/artifacts/.native-staging-identity.json').read_text())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--disable-dev-shm-usage'])
        page = browser.new_page()
        page.goto('http://webui:8080/auth')
        page.locator('input[name="email"]').fill(identity['email'])
        page.locator('input[type="password"]').first.fill(identity['password'])
        page.locator('button[type="submit"]').click()
        composer = page.locator('#chat-input')
        expect(composer).to_be_visible(timeout=30000)
        value = 'SYNTHETIC_PII_OUTAGE_' + uuid.uuid4().hex
        composer.fill(value)
        with page.expect_response(lambda r: '/api/chat/completions/native' in r.url, timeout=30000) as turn:
            composer.press('Enter')
        assert turn.value.status == 503
        assert value not in page.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})')
        db = sqlite3.connect('file:/webui-data/webui.db?mode=ro', uri=True)
        assert value not in '\n'.join(db.iterdump())
        db.close()
        browser.close()