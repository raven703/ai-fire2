"""Local test operator provisioning; never prints credentials or command errors."""
import json
import subprocess
from pathlib import Path

root=Path('/home/user/ai-fire2/artifacts/vault-v2-secrets')
data=json.loads((root/'init.json').read_text())
base=['docker','exec','-i','-e','BAO_ADDR=http://127.0.0.1:8200','-e',
      'BAO_TOKEN='+data['root_token'],'ai-fire2-vault-v2-openbao-1','bao']


def run(args,content=None):
    result=subprocess.run(base+args,input=content,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode: raise SystemExit('OpenBao operation failed (details suppressed)')
    return result.stdout


run(['write','-f','transit/keys/lookup','type=aes256-gcm96'])
policy='\n'.join('path "transit/'+p+'" { capabilities = ["update"] }'
                 for p in ['encrypt/pii','decrypt/pii','hmac/lookup'])
run(['policy','write','vault-service','-'],policy.encode())
token=json.loads(run(['token','create','-policy=vault-service','-orphan','-period=24h','-format=json']))['auth']['client_token']
(root/'bao-token').write_text(token)
(root/'bao-token').chmod(0o600)
print('Restricted service credential provisioned')