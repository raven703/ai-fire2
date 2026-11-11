"""Native service-to-service inspection. No browser credentials, no payload logs."""
import re
import uuid

from fastapi import HTTPException

from ai_firewall.admission import Admission
from ai_firewall.protocol import canonical, schema, text


def native_context(user, chat):
    for value in (user, chat):
        try:
            if not isinstance(value, str) or str(uuid.UUID(value)) != value:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(400, 'invalid_native_scope') from None


async def inspect_batch(data, detector, store, admission: Admission):
    schema(data, {'user', 'chat', 'operation', 'revision', 'fields'})
    native_context(data['user'], data['chat'])
    if data['operation'] not in {'input', 'output', 'chat-write', 'settings', 'model-request'}:
        raise HTTPException(400, 'invalid_operation')
    if not isinstance(data['revision'], str) or not re.fullmatch('[a-f0-9]{64}', data['revision']):
        raise HTTPException(400, 'invalid_revision')
    fields = data['fields']
    if not isinstance(fields, dict) or not 1 <= len(fields) <= 256:
        raise HTTPException(400, 'invalid_fields')
    if any(not isinstance(k, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,120}', k) for k in fields):
        raise HTTPException(400, 'invalid_field_name')
    values = {name: text(value) for name, value in fields.items()}
    if sum(map(len, values.values())) > 128000:
        raise HTTPException(413, 'batch_too_large')
    # Two phases: EVERY field must pass ALL policies before the first Vault call.
    matches = {}
    try:
        for name, value in values.items():
            matches[name] = detector.inspect(value)
    except Exception:
        raise HTTPException(503, 'mandatory_detector_failed') from None
    if any('SYNTHETIC_BLOCK_' in value for value in values.values()):
        raise HTTPException(403, 'BLOCK')
    if any('SYNTHETIC_REVIEW_' in value for value in values.values()):
        raise HTTPException(403, 'REVIEW')
    cleaned = dict(values)
    for name, findings in matches.items():
        for finding in reversed(findings):
            token = await store(finding.group(), data['user'], data['chat'])
            if not isinstance(token, str) or not re.fullmatch(r'\[PII_[a-f0-9]{48}\]', token):
                raise HTTPException(503, 'invalid_vault_receipt')
            value = cleaned[name]
            cleaned[name] = value[:finding.start()] + token + value[finding.end():]
    payload = {**data, 'fields': cleaned}
    return {'payload': payload, 'action': 'MASK' if any(matches.values()) else 'ALLOW',
            'admission': admission.issue(canonical(payload), data['user'], data['operation'])}