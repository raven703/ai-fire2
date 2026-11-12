"""Remaining isolated Vault checks. Aggregate output only; preserves all volumes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4

ROOT=Path('/home/user/ai-fire2')
spec=importlib.util.spec_from_file_location('lab',ROOT/'scripts/accept-vault-v2-isolated.py')
lab=importlib.util.module_from_spec(spec); spec.loader.exec_module(lab)
RUN_ID=uuid4().hex[:12]
BACKUP=lab.LAB/('backup-'+RUN_ID)


def execute(code):
    return lab.run(['docker','exec','-i',lab.PROJECT+'-vault-v2-1','python','-'],code.encode())


PRELUDE="""
import httpx,json,time,concurrent.futures
from pathlib import Path
c=httpx.Client(base_url='http://127.0.0.1:8000',timeout=15)
w={'Authorization':'Bearer '+Path('/run/secrets/write-key').read_text()}
r={'Authorization':'Bearer '+Path('/run/secrets/reveal-key').read_text()}
s={'tenant':'synthetic','user':'acceptance','chat':'remaining'}
v='SYNTHETIC_V2_REMAINING'
def store():
 return c.post('/store-batch',headers=w,json={**s,'values':[v],'verdict':'MASK','policy_version':'synthetic-evaluation-v1'})
def reveal(t): return c.post('/reveal',headers=r,json={**s,'tokens':[t]})
"""


def main():
    cfg=json.loads((lab.LAB/'compose.json').read_text())
    cfg['services']['vault-v2']['environment']['VAULT_V2_TTL']='3600'
    (lab.LAB/'compose.json').write_text(json.dumps(cfg,indent=2))
    lab.compose('up','-d','vault-v2'); time.sleep(3)
    token=json.loads(execute(PRELUDE+"x=store(); assert x.status_code==200; print(json.dumps(x.json()['tokens'][0]))"))
    root=json.loads((lab.LAB/'init.json').read_text())['root_token']
    lab.bao(['write','-f','transit/keys/pii/rotate'],root)
    execute(PRELUDE+f'assert reveal({token!r}).status_code==200')
    print('PASS Transit encryption-key rotation; old mapping readable')
    for role in ('encrypt','decrypt'):
        old=(lab.LAB/role).read_text()
        new=json.loads(lab.bao(['token','create','-policy='+role,'-orphan','-format=json'],root))['auth']['client_token']
        (lab.LAB/role).write_text(new)
        # Self-revocation takes token only via stdin/environment.
        lab.bao(['token','revoke','-self'],old)
        script='read -r BAO_TOKEN; export BAO_TOKEN BAO_ADDR=http://127.0.0.1:8200; bao token lookup -format=json'
        p=subprocess.run(['docker','exec','-i',lab.PROJECT+'-openbao-1','sh','-c',script],
            input=(old+'\n').encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert p.returncode!=0
    execute(PRELUDE+f'assert reveal({token!r}).status_code==200; assert store().status_code==200')
    print('PASS Transit service credentials rotated; old credentials rejected')
    for dependency in ('openbao','postgres'):
        lab.compose('stop',dependency)
        try:
            execute(PRELUDE+f"a=store(); b=reveal({token!r}); assert a.status_code==503 and b.status_code==503; assert v not in a.text+b.text")
        finally:
            lab.compose('start',dependency); time.sleep(3)
            if dependency=='openbao':
                key=json.loads((lab.LAB/'init.json').read_text())['unseal_keys_b64'][0]
                lab.run(['docker','exec','-i',lab.PROJECT+'-openbao-1','sh','-c',
                    'export BAO_ADDR=http://127.0.0.1:8200; bao write -format=json sys/unseal -'],json.dumps({'key':key}).encode())
        print('PASS '+dependency+' outage STORE/REVEAL fail-closed')
    execute(PRELUDE+"""
def operation(i):
 if i%3==0: return store().status_code
 if i%3==1:
  x=store()
  return reveal(x.json()['tokens'][0]).status_code if x.status_code==200 else x.status_code
 return c.post('/delete-context',headers=w,json=s).status_code
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
 codes=list(pool.map(operation,range(48)))
assert set(codes)<={200,404}, codes
assert store().status_code==200
""")
    print('PASS 48 concurrent STORE/REVEAL/DELETE operations; no server errors')
    execute(PRELUDE+"""
import psycopg
for i in range(3):
 subject={'tenant':'tenant'+str(i),'user':'user'+str(i),'chat':'chat'+str(i)}
 response=c.post('/store-batch',headers=w,json={**subject,'values':[v+str(i)],'verdict':'MASK','policy_version':'synthetic-evaluation-v1'})
 assert response.status_code==200
with psycopg.connect(host='postgres',dbname='vault',user='vault',password=Path('/run/secrets/pg-password').read_text()) as db:
 assert db.execute('SELECT count(*) FROM (SELECT scope,lookup FROM mappings GROUP BY scope,lookup HAVING count(*)>1) AS duplicates').fetchone()[0]==0
 for token,scope,cipher,expires in db.execute('SELECT token,scope,ciphertext,expires FROM mappings'):
  assert cipher.startswith('vault:v') and v not in cipher and expires>time.time()
  assert len(token)==69
""")
    print('PASS post-race DB uniqueness/ciphertext invariants and multi-scope fixtures')
    BACKUP.mkdir(mode=0o700,exist_ok=True)
    # Quiesce writers for a paired logical DB and cold OpenBao file snapshot.
    lab.compose('stop','vault-v2')
    dump=lab.run(['docker','exec',lab.PROJECT+'-postgres-1','pg_dump','-U','vault','-d','vault','-Fc'])
    path=BACKUP/'postgres.dump'; path.write_bytes(dump); path.chmod(0o600)
    lab.compose('stop','openbao')
    lab.run(['docker','cp',lab.PROJECT+'-openbao-1:/bao/data',str(BACKUP/'bao-data')])
    print('PASS paired backup created with writers and OpenBao quiesced')
    # Separate restore project and volumes; no working or source-lab volume reuse.
    restore='ai-fire2-v2-restore-'+RUN_ID
    cfg['services']['vault-v2']['volumes']=[x for x in cfg['services']['vault-v2']['volumes']]
    path=BACKUP/'compose.json'; path.write_text(json.dumps(cfg))
    def rc(*args): return lab.run(['docker','compose','-p',restore,'-f',str(path),*args])
    try:
        rc('up','-d','postgres','openbao'); time.sleep(3); rc('stop','openbao')
        lab.run(['docker','cp',str(BACKUP/'bao-data')+'/.',restore+'-openbao-1:/bao/data'])
        # docker cp without archive mode assigns destination ownership to root.
        # OpenBao runs as UID 100; its 0700 core directory must remain readable.
        lab.run(['docker','run','--rm','--network','none','--user','0',
            '-v',restore+'_bao:/restore','--entrypoint','chown',
            'openbao/openbao:2.5.0','-R','100:1000','/restore'])
        rc('start','openbao'); time.sleep(3)
        key=json.loads((lab.LAB/'init.json').read_text())['unseal_keys_b64'][0]
        lab.run(['docker','exec','-i',restore+'-openbao-1','sh','-c',
            'export BAO_ADDR=http://127.0.0.1:8200; bao write -format=json sys/unseal -'],json.dumps({'key':key}).encode())
        lab.run(['docker','exec','-i',restore+'-postgres-1','pg_restore','-U','vault','-d','vault','--clean','--if-exists'],dump)
        rc('up','-d','vault-v2'); time.sleep(3)
        code=PRELUDE+"""
import psycopg
with psycopg.connect(host='postgres',dbname='vault',user='vault',password=Path('/run/secrets/pg-password').read_text()) as db:
 rows=db.execute('SELECT token,scope,ciphertext FROM mappings').fetchall()
 assert len(rows)>=4
 for t,context,cipher in rows:
  assert v not in cipher
  tenant,user,chat=json.loads(context)
  subject={'tenant':tenant,'user':user,'chat':chat}
  response=c.post('/reveal',headers=r,json={**subject,'tokens':[t]})
  assert response.status_code==200
  assert response.json()['values'][t].startswith(v)
  for field in ('tenant','user','chat'):
   assert c.post('/reveal',headers=r,json={**subject,field:'foreign','tokens':[t]}).status_code==404
 t,context,cipher=rows[0]
 db.execute('UPDATE mappings SET ciphertext=%s WHERE token=%s',('vault:v1:damaged',t)); db.commit()
 tenant,user,chat=json.loads(context)
 denied=c.post('/reveal',headers=r,json={'tenant':tenant,'user':user,'chat':chat,'tokens':[t]})
 assert denied.status_code==503 and v not in denied.text
"""
        lab.run(['docker','exec','-i',restore+'-vault-v2-1','python','-'],code.encode())
        print('PASS separate-project restore decrypts existing backup mappings')
    finally:
        rc('stop')
        lab.compose('start','openbao'); time.sleep(3)
        key=json.loads((lab.LAB/'init.json').read_text())['unseal_keys_b64'][0]
        lab.run(['docker','exec','-i',lab.PROJECT+'-openbao-1','sh','-c',
            'export BAO_ADDR=http://127.0.0.1:8200; bao write -format=json sys/unseal -'],json.dumps({'key':key}).encode())
        lab.compose('start','vault-v2')


if __name__=='__main__':
    try: main()
    except Exception: raise SystemExit('FAIL remaining acceptance; sensitive details suppressed; copies retained') from None