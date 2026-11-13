"""Renew existing scoped periodic tokens; never log headers, tokens or response bodies."""
import time
from pathlib import Path
import httpx

while True:
    healthy=True
    for name in ('vault-encrypt','vault-decrypt'):
        try:
            token=Path('/run/secrets/'+name).read_text().strip()
            response=httpx.post('http://openbao:8200/v1/auth/token/renew-self',json={},
                headers={'X-Vault-Token':token},timeout=10,trust_env=False)
            if response.status_code!=200:raise ValueError()
        except Exception:healthy=False
    if healthy:
        Path('/tmp/renewed').write_text(str(int(time.time())))
    print('transit_renewal '+('SUCCESS' if healthy else 'FAILED'),flush=True)
    time.sleep(3600 if healthy else 60)