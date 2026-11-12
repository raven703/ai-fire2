"""Short-lived server-only approval; no plaintext is included in the proof."""
import hashlib
import hmac
import json
import time


def digest(values):
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def issue(key, user, chat, revision, values, synthetic=False):
    body={'user':user,'chat':chat,'revision':revision,'digest':digest(values),'expires':int(time.time())+60,'synthetic':synthetic}
    body['signature']=hmac.new(key.encode(),json.dumps(body,sort_keys=True).encode(),hashlib.sha256).hexdigest()
    return body


def verify(key,proof,user,chat,revision,values):
    try:
        body=dict(proof); signature=body.pop('signature')
        return (set(body)=={'user','chat','revision','digest','expires','synthetic'}
            and type(body['synthetic']) is bool
            and body['user']==user and body['chat']==chat and body['revision']==revision
            and body['digest']==digest(values) and time.time()<body['expires']<=time.time()+65
            and hmac.compare_digest(signature,hmac.new(key.encode(),json.dumps(body,sort_keys=True).encode(),hashlib.sha256).hexdigest()))
    except (ValueError,TypeError,KeyError): return False