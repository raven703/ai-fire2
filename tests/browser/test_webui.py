"""Chromium against the actual compiled protected SvelteKit frontend and OWUI DB."""
import json
import os
import re
import sqlite3
import uuid
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

BASE = 'http://webui:8080'


@pytest.fixture
def browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--disable-dev-shm-usage',
            '--unsafely-treat-insecure-origin-as-secure=http://webui:8080'])
        expect.set_options(timeout=15000)
        yield browser
        browser.close()


def login(page, key='USER_KEY'):
    page.goto(BASE)
    page.get_by_label('Ключ доступа', exact=True).fill(os.environ[key])
    page.get_by_role('button', name='Войти', exact=True).click()
    expect(page.get_by_test_id('open-webui-chat')).to_be_visible()


def send(page, value, count):
    page.get_by_label('Сообщение', exact=True).fill(value)
    page.get_by_role('button', name='Отправить', exact=True).click()
    expect(page.get_by_test_id('message')).to_have_count(count, timeout=20000)
    expect(page.get_by_label('Сообщение', exact=True)).to_be_enabled()


def snapshot():
    db = sqlite3.connect('file:/webui-data/webui.db?mode=ro', uri=True)
    try:
        return '\n'.join(db.iterdump())
    finally:
        db.close()


def storage(page):
    return page.evaluate('''async () => ({
      local: {...localStorage}, session: {...sessionStorage},
      databases: await indexedDB.databases(), caches: typeof caches === 'undefined' ? [] : await caches.keys(),
      workers: navigator.serviceWorker ? (await navigator.serviceWorker.getRegistrations()).length : 0
    })''')


def test_full_svelte_chat_display_history_security_and_storage(browser):
    if os.getenv('FAULT_MODE') == 'gateway-down':
        pytest.skip('normal phase only')
    client = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = client.new_page()
    errors, console, requests = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: console.append(message.text))
    page.on('request', lambda req: requests.append({'url': req.url, 'body': req.post_data or ''}))
    canary = 'SYNTHETIC_PII_BROWSER_' + uuid.uuid4().hex
    login(page)
    page.get_by_role('button', name='Новый чат', exact=True).click()
    send(page, canary, 2)
    expect(page).to_have_url(re.compile(r'/c/[a-f0-9-]{36}$'))
    cid = page.url.rsplit('/', 1)[-1]
    assert canary not in page.get_by_test_id('message').all_text_contents()[0]
    mask = page.get_by_test_id('message-text').first.inner_text()
    assert '[PII_' in mask and canary not in snapshot()
    assert mask in snapshot()
    page.get_by_role('button', name='Показать оригинал', exact=True).first.click()
    expect(page.get_by_test_id('message-text').first).to_have_text(canary)
    assert canary not in snapshot()
    assert canary not in json.dumps(storage(page))
    # Continue while originals are visible: only the new draft is sent by UI.
    requests.clear()
    send(page, 'Continue using masked history', 4)
    bodies = [json.loads(r['body']) for r in requests if r['url'].endswith('/api/firewall/chat')]
    assert bodies == [{'text': 'Continue using masked history', 'chat_id': cid}]
    last = httpx.get('http://mock:8000/test/last', headers={'Authorization': 'Bearer ' + os.environ['TEST_KEY']}).json()
    assert len(last['messages']) == 3 and canary not in json.dumps(last)
    assert last['messages'][0]['content'] == mask
    # Reload must restore only masked history, not the display-only copy.
    page.reload()
    expect(page.get_by_test_id('message')).to_have_count(4)
    assert canary not in page.locator('body').inner_text()
    expect(page.get_by_test_id('message-text').first).to_have_text(mask)
    send(page, canary, 6)
    expect(page.get_by_test_id('message-text').nth(4)).to_have_text(mask)
    # Blocked original must never enter persisted history.
    blocked = 'SYNTHETIC_BLOCK_' + canary
    before = snapshot()
    page.get_by_label('Сообщение', exact=True).fill(blocked)
    page.get_by_role('button', name='Отправить', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('BLOCK')
    assert before == snapshot()
    expect(page.get_by_test_id('message')).to_have_count(6)
    # Safe text interpolation: no HTML execution, before and after reveal.
    payload = '<img src=x onerror="window.xss=1"> ' + canary
    send(page, payload, 8)
    page.get_by_role('button', name='Показать оригинал', exact=True).last.click()
    expect(page.get_by_test_id('message-text').last).to_have_text(payload)
    assert page.get_by_test_id('message-text').last.locator('img').count() == 0
    assert page.evaluate('window.xss') is None
    # Direct API calls cannot write raw data, even in an authenticated browser.
    for path in ['/api/v1/chats/new', '/api/v1/chats/import', '/api/chat/completions',
                 '/api/v1/files/', '/api/v1/retrieval/process/text', '/api/v1/tools/',
                 '/firewall/save', '/api/firewall/chat?bypass=1']:
        result = page.evaluate('''async ({path, text}) => (await fetch(path, {
          method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})})).status''',
                               {'path': path, 'text': canary})
        assert result == 403
    # Unsupported UI actions are absent, not merely allowed to fail later.
    assert page.locator('input[type=file]').count() == 0
    assert not any('/socket.io/' in r['url'] or '/ws' in r['url'] for r in requests)
    result = storage(page)
    assert canary not in json.dumps(result)
    assert result['databases'] == [] and result['caches'] == [] and result['workers'] == 0
    assert result['local'] == {}
    assert set(result['session']) <= {'sveltekit:scroll', 'sveltekit:snapshot'}
    assert result['session'].get('sveltekit:snapshot', '{}') == '{}'
    assert not errors
    assert canary not in '\n'.join(console)
    assert canary not in snapshot()
    # Cross-user context, including knowledge of a valid Alice chat ID.
    other = browser.new_context()
    bob = other.new_page()
    login(bob, 'USER_B_KEY')
    for operation, body in [('history', {'chat_id': cid}), ('view', {'chat_id': cid}),
                             ('chat', {'chat_id': cid, 'text': 'public'})]:
        status = bob.evaluate('''async ({operation,body}) => (await fetch('/api/firewall/'+operation,
          {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).status''',
                              {'operation': operation, 'body': body})
        assert status == 404
    bob.goto(BASE + '/c/' + cid)
    expect(bob.get_by_role('alert')).to_contain_text('Чат недоступен')
    assert canary not in bob.locator('body').inner_text()
    other.close()
    # A new chat and sidebar selection restore the same server-owned history.
    page.get_by_role('button', name='Новый чат', exact=True).click()
    expect(page.get_by_test_id('message')).to_have_count(0)
    page.goto(BASE + '/c/' + cid)
    expect(page.get_by_test_id('message')).to_have_count(8)
    assert canary not in page.locator('body').inner_text()
    # Screenshot contains masks only; no traces/videos or raw test output written.
    Path('/artifacts').mkdir(exist_ok=True)
    page.screenshot(path='/artifacts/iteration3-masked-chat.png')
    for path in Path('/webui-data').rglob('*'):
        if path.is_file():
            assert canary.encode() not in path.read_bytes(), str(path)
    client.close()


@pytest.mark.skipif(os.getenv('FAULT_MODE') != 'gateway-down', reason='fault phase only')
def test_gateway_outage_fails_closed_in_browser(browser):
    page = browser.new_page()
    # Login works locally, but history and inference require the unavailable Gateway.
    page.goto(BASE)
    page.get_by_label('Ключ доступа', exact=True).fill(os.environ['USER_KEY'])
    page.get_by_role('button', name='Войти', exact=True).click()
    expect(page.get_by_test_id('open-webui-chat')).to_be_visible()
    before = snapshot()
    page.get_by_label('Сообщение', exact=True).fill('SYNTHETIC_PII_OUTAGE_' + uuid.uuid4().hex)
    page.get_by_role('button', name='Отправить', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('не сохранено', timeout=20000)
    expect(page.get_by_test_id('message')).to_have_count(0)
    assert before == snapshot()
    assert 'SYNTHETIC_PII_OUTAGE_' not in snapshot()
    page.close()