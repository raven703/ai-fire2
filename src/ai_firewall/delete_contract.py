"""Strict content-free deletion manifest, never a content admission endpoint."""
import json
import re
from fastapi import HTTPException
from ai_firewall.batch import native_context
from ai_firewall.protocol import schema


def validate_delete(data):
    schema(data,{'user','chat','operation','revision','fields'})
    native_context(data['user'],data['chat'])
    if data['operation']!='chat-delete' or not re.fullmatch('[a-f0-9]{64}',data['revision']):
        raise HTTPException(400,'invalid_delete_manifest')
    if set(data['fields'])!={'rows'} or len(data['fields']['rows'])>1048576:
        raise HTTPException(400,'invalid_delete_manifest')
    rows=json.loads(data['fields']['rows'])
    if not isinstance(rows,list) or not 1<=len(rows)<=4096:
        raise HTTPException(400,'invalid_delete_manifest')
    seen=set();chats=0
    for row in rows:
        if set(row)!={'table','delete','columns'} or row['delete'] is not True or row['table'] not in {'chat','chat_message'}:
            raise HTTPException(400,'delete_only_required')
        columns=row['columns']
        if set(columns)!={'id','row_sha256'} or not re.fullmatch('[a-f0-9]{64}',columns['row_sha256']):
            raise HTTPException(400,'invalid_delete_digest')
        identifier=columns['id']
        if row['table']=='chat':
            if identifier!=data['chat']: raise HTTPException(400,'invalid_delete_scope')
            chats+=1
        elif not re.fullmatch(re.escape(data['chat'])+r'-[a-f0-9-]{36}',identifier):
            raise HTTPException(400,'invalid_delete_scope')
        pair=(row['table'],identifier)
        if pair in seen: raise HTTPException(400,'duplicate_delete_row')
        seen.add(pair)
    if chats!=1: raise HTTPException(400,'delete_chat_required')
    return data