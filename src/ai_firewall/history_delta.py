"""Append-only canonical history delta; no deletion/edit of prior message content."""
from copy import deepcopy
from fastapi import HTTPException
from ai_firewall.protocol import canonical
import hashlib


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def changed_fields(before, after):
    """Validate persisted message identity before excluding it from NLP inspection."""
    if before and 'chat_id' in before:
        if any(before.get(k)!=after.get(k) for k in before if k!='updated_at'):
            raise HTTPException(403,'native_message_row_modified')
    old=before.get('chat',{}).get('history',{}).get('messages',{})
    new=after.get('chat',{}).get('history',{}).get('messages',{})
    if not set(old)<=set(new):raise HTTPException(403,'native_history_removed')
    added=set(new)-set(old)
    for identifier,item in old.items():
        candidate=deepcopy(new[identifier])
        previous=deepcopy(item)
        children=previous.pop('childrenIds',[])
        next_children=candidate.pop('childrenIds',[])
        if candidate!=previous:raise HTTPException(403,'native_history_modified')
        if next_children!=children:
            if children or len(next_children)!=1 or next_children[0] not in added:
                raise HTTPException(403,'native_history_link_modified')
            if new[next_children[0]].get('parentId')!=identifier:raise HTTPException(403,'native_history_link_invalid')
    # Only persisted immutable messages are omitted. All other changed columns,
    # metadata, titles and new messages remain covered by the Gateway.
    reduced=deepcopy(after)
    if 'chat' in reduced:
        doc=reduced['chat']
        if 'messages' in doc:raise HTTPException(403,'native_legacy_history_forbidden')
        if 'history' in doc:doc['history']['messages']={k:v for k,v in new.items() if k in added}
    return {k:v for k,v in reduced.items() if k not in before or before[k]!=after[k]}