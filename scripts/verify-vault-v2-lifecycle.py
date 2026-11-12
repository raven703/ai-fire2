"""Synthetic lifecycle tests inside Vault container; aggregate-only output."""
import concurrent.futures
import os
import time
from pathlib import Path
import httpx
import psycopg

headers={'Authorization':'Bearer '+Path('/run/secrets/write-key').read_text().strip()}
rh={'Authorization':'Bearer '+Path('/run/secrets/reveal-key').read_text().strip()}
context={'tenant':'synthetic','user':'lifecycle','chat':'parallel'}
value='SYNTHETIC_V2_'+os.urandom(16).hex()
def store():
    r=httpx.post('http://127.0.0.1:8000/store-batch',headers=headers,json={**context,
        'values':[value],'verdict':'MASK','policy_version':'synthetic-evaluation-v1'},timeout=30)
    r.raise_for_status(); return r.json()['tokens'][0]
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    tokens=list(pool.map(lambda _:store(),range(12)))
assert len(set(tokens))==1
token=tokens[0]
def read(): return httpx.post('http://127.0.0.1:8000/reveal',headers=rh,json={**context,'tokens':[token]})
assert read().status_code==200
password=Path('/run/secrets/pg-password').read_text().strip()
with psycopg.connect(host='postgres',dbname='vault',user='vault',password=password) as db:
    assert db.execute('SELECT count(*) FROM mappings WHERE token=%s',(token,)).fetchone()[0]==1
    db.execute('UPDATE mappings SET expires=%s WHERE token=%s',(int(time.time())-1,token))
assert read().status_code==404
assert store()!=token
print('PASS concurrent scoped reuse, unique row, expired mapping denial and replacement')