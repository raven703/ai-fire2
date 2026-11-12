"""Run inside Vault v2 container; aggregate assertions, no plaintext output."""
import os
import time
from pathlib import Path
import httpx
import psycopg

base='http://127.0.0.1:8000'
write={'Authorization':'Bearer '+Path('/run/secrets/write-key').read_text().strip()}
reveal={'Authorization':'Bearer '+Path('/run/secrets/reveal-key').read_text().strip()}
scope={'tenant':'synthetic','user':'test-user','chat':'test-chat'}
value='SYNTHETIC_V2_'+os.urandom(16).hex()
for _ in range(30):
    try:
        if httpx.get(base+'/health').status_code==200: break
    except httpx.HTTPError: pass
    time.sleep(1)
else: raise SystemExit('readiness failed')
def store(verdict='MASK',context=scope):
    return httpx.post(base+'/store-batch',headers=write,json={**context,'values':[value],
        'verdict':verdict,'policy_version':'synthetic-evaluation-v1'})
def read(token,context=scope):
    return httpx.post(base+'/reveal',headers=reveal,json={**context,'tokens':[token]})
r=store(); assert r.status_code==200
token=r.json()['tokens'][0]
assert store().json()['tokens'][0]==token
assert read(token).json()['values'][token]==value
assert read(token,{**scope,'user':'foreign'}).status_code==404
assert read(token,{**scope,'chat':'foreign'}).status_code==404
assert read(token,{**scope,'tenant':'foreign'}).status_code==404
assert store(context={**scope,'user':'foreign'}).json()['tokens'][0]!=token
assert store('BLOCK').status_code==403 and store('REVIEW').status_code==403
assert httpx.post(base+'/reveal',headers=write,json={**scope,'tokens':[token]}).status_code==403
with psycopg.connect(host='postgres',dbname='vault',user='vault',password=Path('/run/secrets/pg-password').read_text().strip()) as db:
    rows=db.execute('SELECT * FROM mappings').fetchall()
    assert value not in str(rows)
    original=db.execute('SELECT ciphertext FROM mappings WHERE token=%s',(token,)).fetchone()[0]
    db.execute('UPDATE mappings SET ciphertext=%s WHERE token=%s',(original[:-4]+'AAAA',token))
assert read(token).status_code==503
with psycopg.connect(host='postgres',dbname='vault',user='vault',password=Path('/run/secrets/pg-password').read_text().strip()) as db:
    db.execute('UPDATE mappings SET ciphertext=%s WHERE token=%s',(original,token))
assert read(token).status_code==200
httpx.post(base+'/delete-context',headers=write,json=scope).raise_for_status()
assert read(token).status_code==404
print('PASS encryption roundtrip, stable reuse, scope isolation, BLOCK/REVIEW, role separation, ciphertext tamper, deletion, DB plaintext absence')