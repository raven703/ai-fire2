"""Exact, short-lived model-only approval. Never valid for a history writer."""
import hashlib
import json
import time
from ai_firewall.admission import Admission
from ai_firewall.protocol import canonical
from fastapi import HTTPException


def scope(event, fields, user, chat, policy):
    return dict(event=event, fields_hash=hashlib.sha256(canonical(fields)).hexdigest(),
                tenant='synthetic', user=user, chat=chat, policy=policy)


def issue(key, claims):
    return Admission(key.encode(), 'review-model-v1').issue(canonical(claims), claims['user'], 'review-model')


def verify(key, token, claims):
    if not Admission(key.encode(), 'review-model-v1').verify(token, canonical(claims), claims['user'], 'review-model'):
        raise HTTPException(403, 'review_permit_invalid')
    return json.loads(bytes.fromhex(token.split('.')[0]))['nonce']