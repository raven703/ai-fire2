"""Create an isolated synthetic acceptance lab; never mounts working volumes.

Run from the repository root. Secrets stay in ignored artifacts with mode 0600.
Operator commands never put credentials in argv or emit subprocess errors.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path('/home/user/ai-fire2')
LAB = ROOT / 'artifacts/vault-v2-acceptance'
PROJECT = 'ai-fire2-v2-acceptance'


def run(args, data=None):
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Acceptance subprocess failed; sensitive diagnostics suppressed')
    return result.stdout


def compose(*args):
    return run(['docker', 'compose', '-p', PROJECT, '-f', str(LAB / 'compose.json'), *args])


def bao(args, token=None):
    script = 'export BAO_ADDR=http://127.0.0.1:8200; '
    if token:
        script += 'read -r BAO_TOKEN; export BAO_TOKEN; '
    script += 'exec bao "$@"'
    return run(['docker', 'exec', '-i', PROJECT + '-openbao-1', 'sh', '-c', script, 'sh', *args],
               (token + '\n').encode() if token else None)


def main():
    LAB.mkdir(mode=0o700, parents=True, exist_ok=True)
    if (LAB / 'init.json').exists():
        raise RuntimeError('Initialized lab already exists; preserve evidence')
    for name in ('pg-password', 'write-key', 'reveal-key'):
        path = LAB / name
        path.write_text(secrets.token_hex(32)); path.chmod(0o600)
    def mount(name, dest=None):
        return f'{LAB / name}:/run/secrets/{dest or name}:ro'
    services = {
        'postgres': {'image': 'postgres:17.7-bookworm', 'environment': {
            'POSTGRES_DB': 'vault', 'POSTGRES_USER': 'vault',
            'POSTGRES_PASSWORD_FILE': '/run/secrets/pg-password'},
            'volumes': ['pg:/var/lib/postgresql/data', mount('pg-password'),
                f'{ROOT}/config/vault-v2-schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro'],
            'mem_limit': '192m'},
        'openbao': {'image': 'openbao/openbao:2.5.0',
            'command': ['server', '-config=/bao/config/test.hcl'],
            'volumes': ['bao:/bao/data', f'{ROOT}/config/vault-v2-bao.hcl:/bao/config/test.hcl:ro'],
            'mem_limit': '192m'},
        'vault-v2': {'image': 'ai-fire2-vault-v2-vault-v2', 'environment': {
            'PG_PASSWORD_FILE': '/run/secrets/pg-password',
            'BAO_TOKEN_FILE': '/run/secrets/encrypt', 'BAO_DECRYPT_TOKEN_FILE': '/run/secrets/decrypt',
            'VAULT_WRITE_KEY_FILE': '/run/secrets/write-key',
            'VAULT_REVEAL_KEY_FILE': '/run/secrets/reveal-key',
            'BAO_URL': 'http://openbao:8200', 'VAULT_V2_TTL': '4'},
            'volumes': [mount(n) for n in ('pg-password','write-key','reveal-key','encrypt','decrypt')],
            'mem_limit': '128m', 'read_only': True, 'tmpfs': ['/tmp']}}
    for service in services.values():
        service['networks'] = ['lab']
    (LAB / 'compose.json').write_text(json.dumps({'services': services,
        'volumes': {'pg': {}, 'bao': {}}, 'networks': {'lab': {'internal': True}}}, indent=2))
    compose('up', '-d', 'postgres', 'openbao')
    # File storage directory must be owned by the OpenBao container user.
    run(['docker','exec','-u','0',PROJECT+'-openbao-1','chown','100:1000','/bao/data'])
    compose('restart','openbao')
    time.sleep(3)
    initialized = json.loads(bao(['operator','init','-key-shares=1','-key-threshold=1','-format=json']))
    path=LAB/'init.json'; path.write_text(json.dumps(initialized)); path.chmod(0o600)
    # Unseal share is provided over stdin, never command arguments.
    def unseal():
        run(['docker','exec','-i',PROJECT+'-openbao-1','sh','-c',
             'export BAO_ADDR=http://127.0.0.1:8200; bao write sys/unseal -'],
            json.dumps({'key':initialized['unseal_keys_b64'][0]}).encode())
    unseal()
    root=initialized['root_token']
    bao(['secrets','enable','transit'],root)
    for key in ('pii','lookup'):
        bao(['write','-f','transit/keys/'+key,'type=aes256-gcm96'],root)
    for name,paths in {'encrypt':['encrypt/pii','hmac/lookup'], 'decrypt':['decrypt/pii']}.items():
        policy='\n'.join('path "transit/'+p+'" { capabilities = ["update"] }' for p in paths)
        run(['docker','exec','-i',PROJECT+'-openbao-1','sh','-c',
            'read -r BAO_TOKEN; export BAO_TOKEN BAO_ADDR=http://127.0.0.1:8200; bao policy write "$1" -',
            'sh',name],(root+'\n'+policy).encode())
        credential=json.loads(bao(['token','create','-policy='+name,'-orphan','-format=json'],root))['auth']['client_token']
        path=LAB/name; path.write_text(credential); path.chmod(0o600)
    compose('up','-d','vault-v2')
    time.sleep(5)
    test = '''
import time,httpx,json
from pathlib import Path
c=httpx.Client(base_url='http://127.0.0.1:8000',timeout=15)
w={'Authorization':'Bearer '+Path('/run/secrets/write-key').read_text()}
r={'Authorization':'Bearer '+Path('/run/secrets/reveal-key').read_text()}
s={'tenant':'synthetic','user':'acceptance','chat':'ttl'}
v='SYNTHETIC_V2_REAL_WAIT'
response=c.post('/store-batch',headers=w,json={**s,'values':[v],'verdict':'MASK','policy_version':'synthetic-evaluation-v1'})
assert response.status_code==200
t=response.json()['tokens'][0]
assert c.post('/reveal',headers=r,json={**s,'tokens':[t]}).status_code==200
for key in ('tenant','user','chat'):
 assert c.post('/reveal',headers=r,json={**s,key:'foreign','tokens':[t]}).status_code==404
time.sleep(5)
assert c.post('/reveal',headers=r,json={**s,'tokens':[t]}).status_code==404
print('PASS real-wait TTL and tenant/user/chat isolation')
'''
    print(run(['docker','exec','-i',PROJECT+'-vault-v2-1','python','-'],test.encode()).decode().strip())
    compose('restart','postgres','openbao','vault-v2')
    time.sleep(3); unseal(); time.sleep(3)
    health="import httpx; assert httpx.get('http://127.0.0.1:8000/health').status_code==200; print('PASS restart and unseal readiness')"
    print(run(['docker','exec',PROJECT+'-vault-v2-1','python','-c',health]).decode().strip())
    print('Lab retained; isolated volumes and recovery material are NOT production accepted')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('FAIL isolated acceptance; details suppressed; lab retained') from None