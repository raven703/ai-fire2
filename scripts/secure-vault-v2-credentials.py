"""One-time local containment. Secrets travel via stdin, never argv or output."""
import json
import subprocess
from pathlib import Path

root=Path('/home/user/ai-fire2/artifacts/vault-v2-secrets')
data=json.loads((root/'init.json').read_text())
payload={'root':data.get('root_token'),'service':(root/'bao-token').read_text().strip()}
code=r'''
import json,sys,httpx
d=json.load(sys.stdin)
url='http://openbao:8200/v1/'
def call(path,data=None,token=None,method='POST'):
    r=httpx.request(method,url+path,json=data,headers={'X-Vault-Token':token or d['root']},timeout=5,trust_env=False)
    if r.status_code>=400: raise RuntimeError('credential_operation_failed')
    return r.json() if r.content else {}
call('auth/token/lookup-self',token=d['root'],method='GET')
policies={
 'vault-encrypt':'path "transit/encrypt/pii" { capabilities = ["update"] }\npath "transit/hmac/lookup" { capabilities = ["update"] }',
 'vault-decrypt':'path "transit/decrypt/pii" { capabilities = ["update"] }',
 'vault-operator':'path "transit/keys/pii/rotate" { capabilities = ["update"] }\npath "transit/rewrap/pii" { capabilities = ["update"] }\npath "transit/keys/pii" { capabilities = ["read"] }'
}
tokens={}
for name,policy in policies.items():
    call('sys/policies/acl/'+name,{'policy':policy})
    tokens[name]=call('auth/token/create-orphan',{'policies':[name],'period':'24h','no_default_policy':True})['auth']['client_token']
call('auth/token/revoke',{'token':d['service']})
call('auth/token/revoke-self',{},token=d['root'])
r=httpx.get(url+'auth/token/lookup-self',headers={'X-Vault-Token':d['root']},trust_env=False)
if r.status_code!=403: raise RuntimeError('root_revocation_unconfirmed')
print(json.dumps(tokens))
'''
program=code+'\n'
# Docker exec stdin contains the program and JSON in one bounded invocation.
wrapper='import sys; exec('+repr(program)+')'
result=subprocess.run(['docker','exec','-i','ai-fire2-vault-v2-vault-v2-1','python','-c',wrapper],
    input=json.dumps(payload).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
if result.returncode: raise SystemExit('Containment failed; operations must stop. Details suppressed.')
tokens=json.loads(result.stdout)
for name,token in tokens.items():
    path=root/name; path.write_text(token); path.chmod(0o600)
# Keep unseal shares, remove revoked root value from recovery metadata.
data.pop('root_token',None)
(root/'init.json').write_text(json.dumps(data)); (root/'init.json').chmod(0o600)
old=payload['root'].encode()
hits=[]
for path in Path('/home/user/ai-fire2').joinpath('artifacts').rglob('*'):
    if path.is_file() and path.stat().st_size<20_000_000:
        try:
            raw=path.read_bytes()
            if old in raw:
                hits.append(str(path.relative_to(root.parent)))
                path.write_bytes(raw.replace(old,b'[REVOKED_SECRET_REMOVED]'))
        except OSError: pass
(root/'bao-token').unlink(missing_ok=True)
print('PASS root revoked and rejection verified; old service revoked; split credentials provisioned; artifact secret matches sanitized:',len(hits))