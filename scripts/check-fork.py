"""Read-only provenance check; never reset/clean an existing fork checkout."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'fork-manifest.json').read_text())
fork = root / manifest['local_path']


def git(*args):
    return subprocess.check_output(['git', '-C', str(fork), *args], text=True).strip()


assert git('branch', '--show-current') == manifest['development_branch']
subprocess.run(['git', '-C', str(fork), 'merge-base', '--is-ancestor',
                manifest['upstream_commit'], 'HEAD'], check=True)
assert git('remote', 'get-url', 'upstream') == manifest['upstream_url']
assert git('remote', 'get-url', '--push', 'upstream') == 'DISABLED'
for name in ['LICENSE', 'LICENSE_HISTORY', 'LICENSE_NOTICE']:
    assert (fork / name).is_file(), name
print('PASS: fork ancestry, branch, upstream provenance and license files')
print('Native security acceptance: NOT completed')