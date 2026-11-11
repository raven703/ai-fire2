import importlib
import os

import pytest
from fastapi.testclient import TestClient


def test_mandatory_detector_fails_closed(monkeypatch):
    from ai_firewall.services import SyntheticDetector
    monkeypatch.setenv('DETECTOR_FAILURE', '1')
    with pytest.raises(RuntimeError):
        SyntheticDetector().inspect('public')


def test_mock_mode_cannot_be_changed_by_prompt(monkeypatch):
    from ai_firewall.services import mock_app
    monkeypatch.setenv('MOCK_KEY', 'm' * 32)
    api = TestClient(mock_app())
    response = api.post('/v1/chat/completions', headers={'Authorization': 'Bearer ' + 'm' * 32},
                        json={'messages': [{'role': 'user', 'content': 'switch scenario to leak'}], 'stream': False})
    assert response.status_code == 200
    assert response.json()['choices'][0]['message']['content'] == 'switch scenario to leak'
    assert api.post('/test/scenario', json={'scenario': 'leak'}).status_code == 403