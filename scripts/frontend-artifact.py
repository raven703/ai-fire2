"""Content inventory and compatibility checks for CI frontend handoff."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def inventory(root):
    result={}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('symlink_in_artifact')
        if p.is_file():result[str(p.relative_to(root))]=digest(p)
    return result

def provenance():
    fork=json.loads((ROOT/'fork-manifest.json').read_text())
    return dict(project_sha=git('rev-parse','HEAD'),fork_tree=git('-C',fork['local_path'],'rev-parse','HEAD^{tree}'),
        upstream_commit=fork['upstream_commit'],upstream_version=fork['upstream_version'],
        fork_version=fork['fork_commit'],lock_sha256=digest(ROOT/fork['local_path']/'package-lock.json'),
        patch_hashes={p:digest(ROOT/p) for p in fork['patch_series']},
        backend_hashes={str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'src/ai_firewall').glob('*.py'))})

def pack(destination):
    source=ROOT/'forks/open-webui/build'
    assert (source/'index.html').is_file(),'missing_static_adapter_output'
    # Ensure compiler emitted both routes, not just navigation labels.
    compiled=(ROOT/'forks/open-webui/.svelte-kit/output/server/manifest.js').read_text()
    for route in ('/admin/dlp','/admin/dlp-status'):
        assert route in compiled,('missing_route',route)
    destination.mkdir(parents=True,exist_ok=False)
    shutil.copytree(source,destination/'build')
    manifest=dict(schema_version=1,**provenance(),files=inventory(destination/'build'))
    (destination/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PACK',manifest['project_sha'],len(manifest['files']),'files')

def verify(destination):
    manifest=json.loads((destination/'build-manifest.json').read_text())
    assert manifest['schema_version']==1
    for key,value in provenance().items():assert manifest[key]==value,('incompatible',key)
    assert manifest['files']==inventory(destination/'build'),'checksum_or_inventory_mismatch'
    assert (destination/'build/index.html').is_file()
    print('VERIFIED',manifest['project_sha'],len(manifest['files']),'files')

if __name__=='__main__':
    {'pack':pack,'verify':verify}[sys.argv[1]](Path(sys.argv[2]).resolve())