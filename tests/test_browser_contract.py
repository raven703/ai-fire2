"""Session and CSRF checks against real protected WebUI (no mocked auth)."""
import os

import httpx
import pytest
from test_integration import ready

pytestmark = pytest.mark.skipif(os.getenv('RUN_INTEGRATION') != '1', reason='Compose only')


def test_real_browser_session_csrf_and_logout():
    with httpx.Client(base_url='http://webui:8080', trust_env=False) as client:
        origin = {'Origin': 'http://webui:8080'}
        assert client.get('/api/firewall/session').status_code == 403
        assert client.post('/api/firewall/login', json={'key': os.environ['USER_KEY']}).status_code == 403
        assert client.post('/api/firewall/login', json={'key': os.environ['USER_KEY']},
                           headers={'Origin': 'http://evil.invalid'}).status_code == 403
        response = client.post('/api/firewall/login', json={'key': os.environ['USER_KEY']}, headers=origin)
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
        assert 'Max-Age' not in response.headers['set-cookie']
        assert client.get('/api/firewall/session').json()['user'] == 'synthetic-user'
        assert client.post('/api/firewall/chat', json={'text': 'public'}).status_code == 403
        assert client.post('/api/firewall/logout', json={}, headers=origin).status_code == 200
        assert client.get('/api/firewall/session').status_code == 403