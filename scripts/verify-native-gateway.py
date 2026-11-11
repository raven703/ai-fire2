"""Run inside native gateway container: live contract, never print originals."""
import os
import uuid

import httpx

headers = {'Authorization': 'Bearer ' + os.environ['NATIVE_GATEWAY_KEY']}
scope = dict(user=str(uuid.uuid4()), chat=str(uuid.uuid4()), operation='input', revision='0' * 64)
with httpx.Client(base_url='http://localhost:8000', trust_env=False, timeout=15) as client:
    assert client.post('/native/inspect', json={}).status_code == 403
    for verdict in ['BLOCK', 'REVIEW']:
        response = client.post('/native/inspect', headers=headers, json={**scope, 'fields': {
            'first': 'SYNTHETIC_PII_DENIED_' + scope['chat'].replace('-', ''),
            'last': 'SYNTHETIC_' + verdict + '_DENY'}})
        assert response.status_code == 403
    response = client.post('/native/inspect', headers=headers, json={**scope, 'fields': {'a': {
        'nested': 'SYNTHETIC_PII_NESTED'}}})
    assert response.status_code == 400
    response = client.post('/native/inspect', headers=headers, json={**scope, 'fields': {
        'first': 'SYNTHETIC_PII_APPROVED_' + scope['chat'].replace('-', '')}})
    assert response.status_code == 200
    assert 'SYNTHETIC_PII_' not in response.text
print('PASS live authenticated native batch: auth, BLOCK, REVIEW, nested schema, MASK')