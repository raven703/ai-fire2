"""Run inside isolated acceptance Vault only; synthetic partial-commit model."""
import concurrent.futures
import time
from pathlib import Path

import httpx
import psycopg

c=httpx.Client(base_url='http://127.0.0.1:8000',timeout=20)
w={'Authorization':'Bearer '+Path('/run/secrets/write-key').read_text()}
r={'Authorization':'Bearer '+Path('/run/secrets/reveal-key').read_text()}
scope={'tenant':'synthetic','user':'cleanup','chat':'partial_commit'}
value='SYNTHETIC_V2_ORPHAN_TEST'


def store():
    response=c.post('/store-batch',headers=w,json={**scope,'values':[value],
        'verdict':'MASK','policy_version':'synthetic-evaluation-v1'})
    response.raise_for_status()
    return response.json()['tokens'][0]


def cleanup():
    response=c.post('/cleanup-expired',headers=w,json={})
    response.raise_for_status()
    return response.json()['deleted_count']


token=store()  # Deliberately do not attach to a WebUI message: failed commit.
assert store()==token  # Another successful message may reuse the same token.
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    list(pool.map(lambda _:cleanup(),range(12)))
assert c.post('/reveal',headers=r,json={**scope,'tokens':[token]}).status_code==200
assert c.post('/cleanup-expired',headers=r,json={}).status_code==403
with psycopg.connect(host='postgres',dbname='vault',user='vault',
        password=Path('/run/secrets/pg-password').read_text()) as db:
    db.execute('UPDATE mappings SET expires=%s WHERE token=%s',(int(time.time())-1,token))
cleanup()
assert c.post('/reveal',headers=r,json={**scope,'tokens':[token]}).status_code==404
assert store()!=token
print('PASS orphan bounded retention, live reuse preserved, concurrent cleanup, expiry and role denial')