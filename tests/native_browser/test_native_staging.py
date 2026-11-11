"""Acceptance of staged original UI/auth only, NOT native chat acceptance."""
import json
import re
import secrets
import sqlite3
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect


def test_original_auth_and_closed_content():
    email = 'stage' + uuid.uuid4().hex + '@synthetic.invalid'
    password = secrets.token_urlsafe(32)
    credentials = Path('/artifacts/.native-staging-identity.json')
    if credentials.exists():
        identity = json.loads(credentials.read_text())
        email, password = identity['email'], identity['password']
    api = httpx.Client(base_url='http://webui:8080', timeout=30)
    registered = api.post('/api/v1/auths/signup', json={'name': 'Synthetic Staging',
                                                     'email': email, 'password': password})
    if registered.status_code == 200:
        credentials.write_text(json.dumps({'email': email, 'password': password}))
        credentials.chmod(0o600)
    else:
        assert credentials.exists(), 'First admin already exists; staging test identity unavailable'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--disable-dev-shm-usage'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.goto('http://webui:8080/auth')
        page.locator('input[name="email"]').fill(email)
        page.locator('input[type="password"]').first.fill(password)
        with page.expect_response(lambda response: '/api/v1/auths/signin' in response.url) as login:
            page.locator('button[type="submit"]').click()
        assert login.value.status == 200
        page.screenshot(path='/artifacts/native-auth-staging.png')
        storage = page.evaluate('JSON.stringify({local:{...localStorage}, session:{...sessionStorage}})')
        assert password not in storage
        token = login.value.json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        canary = 'SYNTHETIC_PII_NATIVE_' + uuid.uuid4().hex
        for path in ['/api/chat/completions', '/api/v1/chats/new', '/api/v1/files/', '/api/v1/users/user/settings/update']:
            response = api.post(path, headers=headers, json={'content': canary})
            assert response.status_code == 503, (path, response.status_code)
        db = sqlite3.connect('file:/webui-data/webui.db?mode=ro', uri=True)
        dump = '\n'.join(db.iterdump())
        db.close()
        assert canary not in dump
        assert password not in dump
        assert canary not in page.evaluate('JSON.stringify({local:{...localStorage}, session:{...sessionStorage}})')
        browser.close()