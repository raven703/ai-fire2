"""Remaining native security scenarios against real services and Chromium."""
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect


def login(browser, identity):
    context = browser.new_context()
    # Preserve localhost secure-context APIs while proxying to Docker DNS.
    context.route('http://localhost:8080/**', lambda route: route.fulfill(
        response=route.fetch(url=route.request.url.replace('http://localhost:8080', 'http://webui:8080'))))
    page = context.new_page()
    page.goto('http://localhost:8080/auth')
    page.locator('input[name="email"]').fill(identity['email'])
    page.locator('input[type="password"]').fill(identity['password'])
    with page.expect_response(lambda r: '/auths/signin' in r.url) as result:
        page.locator('button[type="submit"]').click()
    assert result.value.status == 200
    assert result.value.json()['role'] in ('user', 'admin')
    expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
    return context, page, result.value.json()['token']


def submit(page, value):
    page.locator('#chat-input').fill(value)
    with page.expect_response(lambda r: '/api/chat/completions/native' in r.url, timeout=90000) as result:
        page.locator('#chat-input').press('Enter')
    assert result.value.status == 200
    return result.value.json()


def storage_snapshot(page):
    return page.evaluate('''async () => {
      const result = {local: {...localStorage}, session: {...sessionStorage}, dbs: [], caches: [], workers: []};
      for (const info of await indexedDB.databases()) {
        const db = await new Promise((ok, fail) => {const r=indexedDB.open(info.name); r.onsuccess=()=>ok(r.result); r.onerror=()=>fail(r.error);});
        const stores = {};
        for (const name of db.objectStoreNames) {
          stores[name] = await new Promise((ok, fail) => {const r=db.transaction(name).objectStore(name).getAll(); r.onsuccess=()=>ok(r.result); r.onerror=()=>fail(r.error);});
        }
        result.dbs.push({name:info.name, stores}); db.close();
      }
      for (const name of await caches.keys()) {
        const cache=await caches.open(name);
        for (const request of await cache.keys()) {
          const response=await cache.match(request);
          result.caches.push({name, url:request.url, body:await response.text()});
        }
      }
      for (const reg of await navigator.serviceWorker.getRegistrations()) {
        result.workers.push({scope:reg.scope, active:reg.active?.scriptURL, waiting:reg.waiting?.scriptURL, installing:reg.installing?.scriptURL});
      }
      return result;
    }''')


def test_verified_isolation_and_all_storage():
    identities = json.loads(Path('/artifacts/.native-verified-pair.json').read_text())
    control = httpx.Client(base_url='http://mock:8000', headers={'Authorization': 'Bearer '+os.environ['TEST_KEY']})
    control.post('/test/scenario', json={'scenario':'normal'}).raise_for_status()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--disable-dev-shm-usage', '--unsafely-treat-insecure-origin-as-secure=http://webui:8080'])
        a, pa, ta = login(browser, identities[0])
        b, pb, tb = login(browser, identities[1])
        canaries = ['SYNTHETIC_PII_STORAGE_'+uuid.uuid4().hex for _ in range(2)]
        states = [submit(pa, 'Private A '+canaries[0]), submit(pb, 'Private B '+canaries[1])]
        for page, token, own, other in ((pa,ta,states[0],states[1]), (pb,tb,states[1],states[0])):
            headers={'Authorization':'Bearer '+token}
            cid=other['chat']['id']
            response=page.request.get('http://webui:8080/api/v1/chats/'+cid+'/native', headers=headers)
            assert response.status == 404
            listing=page.request.get('http://webui:8080/api/v1/chats/native/list', headers=headers)
            assert cid not in listing.text()
            denied=page.request.post('http://webui:8080/api/chat/completions/native', headers=headers,
                data={'chat_id':cid,'revision':other['revision'], 'parent_id':other['chat']['chat']['history']['currentId'],
                      'message_id':str(uuid.uuid4()),'content':'foreign write'})
            assert denied.status == 404
            for suffix in ('', '/view', '/messages', '/share'):
                response=page.request.post('http://webui:8080/api/v1/chats/'+cid+suffix,
                    headers=headers, data={'chat':{'content':canaries[0]}})
                assert response.status == 503
            # Own reads stay available; raw client history extensions are rejected.
            assert page.request.get('http://webui:8080/api/v1/chats/'+own['chat']['id']+'/native',headers=headers).status == 200
            assert page.request.post('http://webui:8080/api/chat/completions/native',headers=headers,
                data={'message_id':str(uuid.uuid4()),'content':'safe','messages':[{'content':canaries[0]}]}).status == 422
            page.reload()
            expect(page.locator('#chat-input')).to_be_visible(timeout=30000)
            snapshot=storage_snapshot(page)
            assert not snapshot['workers'], 'No unreviewed Service Worker permitted'
            for canary in canaries:
                assert canary not in json.dumps(snapshot)
                assert canary not in page.content()
        db=sqlite3.connect('file:/webui-data/webui.db?mode=ro',uri=True)
        dump='\n'.join(db.iterdump()); db.close()
        assert all(value not in dump for value in canaries)
        a.close(); b.close(); browser.close()


def test_output_transport_outage():
    if os.environ.get('NATIVE_FAULT_MODE') != 'output-gateway-down':
        import pytest
        pytest.skip('host-controlled output transport outage only')
    identity=json.loads(Path('/artifacts/.native-verified-pair.json').read_text())[0]
    control=httpx.Client(base_url='http://mock:8000',headers={'Authorization':'Bearer '+os.environ['TEST_KEY']})
    control.post('/test/scenario',json={'scenario':'timeout'}).raise_for_status()
    previous=control.get('/test/last').json()['messages']
    value='SYNTHETIC_PII_OUTPUT_TRANSPORT_'+uuid.uuid4().hex
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(args=['--disable-dev-shm-usage', '--unsafely-treat-insecure-origin-as-secure=http://webui:8080'])
            context,page,token=login(browser,identity)
            page.locator('#chat-input').fill(value)
            with page.expect_response(lambda r:'/api/chat/completions/native' in r.url,timeout=90000) as result:
                page.locator('#chat-input').press('Enter')
                # Mock captures a fully inspected request before sleeping. Host
                # stops Gateway only after this marker, before output inspection.
                deadline=time.monotonic()+12
                while time.monotonic()<deadline:
                    captured=control.get('/test/last').json()['messages']
                    if captured and captured != previous and '[PII_' in captured[-1]['content']:
                        Path('/artifacts/.output-phase-ready').write_text('ready')
                        break
                    time.sleep(.1)
                else:
                    raise AssertionError('model request not observed')
            assert result.value.status==200
            state=result.value.json()
            assert state['error']=='native_inspection_unavailable'
            assert captured[-1]['content'] == next(iter(state['chat']['chat']['history']['messages'].values()))['content']
            assert len(state['chat']['chat']['history']['messages'])==1
            assert value not in json.dumps(state)
            assert 'Synthetic response.' not in page.locator('body').inner_text()
            assert value not in json.dumps(storage_snapshot(page))
            db=sqlite3.connect('file:/webui-data/webui.db?mode=ro',uri=True)
            rows=db.execute('select role from chat_message where chat_id=?',(state['chat']['id'],)).fetchall()
            assert rows==[('user',)]
            assert value not in '\n'.join(db.iterdump()); db.close()
            context.close(); browser.close()
    finally:
        control.post('/test/scenario',json={'scenario':'normal'}).raise_for_status()