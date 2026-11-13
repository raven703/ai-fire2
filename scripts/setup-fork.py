"""Create a local fork without touching dirty vendor files or existing checkout."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'fork-manifest.json').read_text())
destination = root / manifest['local_path']
if destination.exists():
    subprocess.run(['python3', str(root / 'scripts/check-fork.py')], check=True)
else:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = root / 'vendor/open-webui'
    subprocess.run(['git', 'clone', '--no-hardlinks', '--no-checkout',
                    str(source) if source.exists() else manifest['upstream_url'], str(destination)], check=True)
    subprocess.run(['git', '-C', str(destination), 'remote', 'rename', 'origin', 'source-local'], check=True)
    subprocess.run(['git', '-C', str(destination), 'remote', 'add', 'upstream', manifest['upstream_url']], check=True)
    subprocess.run(['git', '-C', str(destination), 'switch', '-c', manifest['development_branch'],
                    manifest['upstream_commit']], check=True)
    for patch in manifest.get('patch_series', []):
        path=root/patch
        if path.read_bytes().startswith(b'From '):
            subprocess.run(['git', '-C', str(destination), 'am', str(path)], check=True)
        else:
            subprocess.run(['git', '-C', str(destination), 'apply','--check',str(path)],check=True)
            subprocess.run(['git', '-C', str(destination), 'apply','--index',str(path)],check=True)
            subprocess.run(['git', '-C', str(destination), 'commit','-m','Apply '+path.name],check=True)
    for remote in ['source-local', 'upstream']:
        subprocess.run(['git', '-C', str(destination), 'config', f'remote.{remote}.pushurl', 'DISABLED'], check=True)
    subprocess.run(['python3', str(root / 'scripts/check-fork.py')], check=True)