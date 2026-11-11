"""Exercise actual fork hooks with injected storage dependencies; not DB E2E."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import uuid

import pytest
from fastapi import HTTPException


@pytest.fixture
def hooks(monkeypatch):
    path = Path('/fork/backend/open_webui/utils/firewall.py')
    if not path.exists():
        path = Path(__file__).resolve().parents[1] / 'forks/open-webui/backend/open_webui/utils/firewall.py'
    if not path.exists():
        pytest.skip('fork source not mounted')
    spec = importlib.util.spec_from_file_location('native_hooks_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_gate_masks_and_discards_provider_metadata(hooks, monkeypatch):
    class Inspector:
        async def inspect(self, fields, *scope):
            assert fields == {'content': 'SYNTHETIC_PII_OUTPUT'}
            assert scope[2] == 'output'
            return {'content': '[PII_' + 'a' * 48 + ']'}
    monkeypatch.setattr(hooks, 'inspector', Inspector)
    result = asyncio.run(hooks.admit_output({'choices': [{'message': {'role': 'assistant',
        'content': 'SYNTHETIC_PII_OUTPUT'}}], 'untrusted_metadata': 'private'}, types.SimpleNamespace(id=str(uuid.uuid4())), str(uuid.uuid4())))
    assert 'SYNTHETIC_PII' not in str(result)
    assert 'untrusted_metadata' not in result


def test_output_gate_failure_returns_no_output(hooks, monkeypatch):
    class Broken:
        async def inspect(self, *args):
            raise HTTPException(503, 'mandatory_detector_failed')
    monkeypatch.setattr(hooks, 'inspector', Broken)
    with pytest.raises(HTTPException) as error:
        asyncio.run(hooks.admit_output({'choices': [{'message': {'role': 'assistant', 'content': 'unsafe'}}]},
                                      types.SimpleNamespace(id=str(uuid.uuid4())), str(uuid.uuid4())))
    assert error.value.status_code == 503


@pytest.mark.parametrize('message', [{'role': 'assistant', 'content': 'safe', 'tool_calls': []},
                                    {'role': 'assistant', 'content': ['unsafe']},
                                    {'role': 'tool', 'content': 'unsafe'}])
def test_output_extensions_are_denied(hooks, message):
    with pytest.raises(HTTPException):
        asyncio.run(hooks.admit_output({'choices': [{'message': message}]}, types.SimpleNamespace(id='x'), 'x'))


def test_completion_drops_unchecked_fields_and_checks_ownership_first(hooks, monkeypatch):
    class Chats:
        @staticmethod
        async def get_chat_by_id(cid):
            return types.SimpleNamespace(user_id=str(uuid.uuid4()))
    monkeypatch.setitem(sys.modules, 'open_webui.models.chats', types.SimpleNamespace(Chats=Chats))
    user = types.SimpleNamespace(id=str(uuid.uuid4()))
    payload = {'model': 'mock', 'stream': False, 'chat_id': str(uuid.uuid4())}
    with pytest.raises(HTTPException) as error:
        asyncio.run(hooks.admit_completion(payload, user))
    assert error.value.status_code == 404


def test_completion_masked_canonical_message(hooks, monkeypatch):
    monkeypatch.setitem(sys.modules, 'open_webui.models.chats', types.SimpleNamespace(Chats=object()))
    class Inspector:
        async def inspect(self, fields, *args):
            assert fields == {'content': 'SYNTHETIC_PII_INPUT'}
            return {'content': '[PII_' + 'b' * 48 + ']'}
    monkeypatch.setattr(hooks, 'inspector', Inspector)
    user = types.SimpleNamespace(id=str(uuid.uuid4()))
    payload = {'model': 'mock', 'stream': False, 'id': str(uuid.uuid4()), 'parent_id': None,
               'user_message': {'id': str(uuid.uuid4()), 'role': 'user', 'content': 'SYNTHETIC_PII_INPUT'},
               'background_tasks': {'title_generation': True}}
    result, cid, rev = asyncio.run(hooks.admit_completion(payload, user))
    assert 'SYNTHETIC_PII' not in str(result)
    assert result['background_tasks'] == {}
    assert len(rev) == 64
    hooks.valid_id(cid)