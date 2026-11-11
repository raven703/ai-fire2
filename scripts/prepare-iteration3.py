"""Reproducible frontend checkout from pinned Git objects, never dirty vendor files."""
from pathlib import Path
import difflib
import io
import shutil
import subprocess
import tarfile

root = Path('/home/user/ai-fire2')
commit = 'b0e6098e940942281d9c83f3529ea117287a3a22'
checkout = root / '.build/open-webui'
checkout.mkdir(parents=True, exist_ok=True)
if (checkout / 'src').exists():
    shutil.rmtree(checkout / 'src')
archive = subprocess.check_output(['git', '-C', str(root / 'vendor/open-webui'), 'archive', commit])
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
    bundle.extractall(checkout, filter='data')
changes = []
for source in sorted((root / 'frontend').rglob('*')):
    if not source.is_file():
        continue
    relative = source.relative_to(root / 'frontend')
    destination = checkout / relative
    before = destination.read_text() if destination.exists() else ''
    after = source.read_text()
    if not after.endswith('\n'):
        after += '\n'
    changes.append(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile='a/' + str(relative) if before else '/dev/null', tofile='b/' + str(relative))))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(after)
# Keep the upstream branded document/splash, but avoid browser persistence even
# for theme preferences. Do not load a custom script surface in protected mode.
document = checkout / 'src/app.html'
before = document.read_text()
after = before.replace('localStorage?.theme', "'dark'").replace('localStorage.theme', "theme")
after = after.replace("const prefersDarkTheme = window.matchMedia", "let theme = 'dark';\n                const prefersDarkTheme = window.matchMedia")
after = after.replace('<script src="/static/loader.js" defer crossorigin="use-credentials"></script>', '')
after = after.replace('<link rel="stylesheet" href="/static/custom.css" crossorigin="use-credentials" />', '')
after = '\n'.join(line.rstrip() for line in after.splitlines()) + '\n'
changes.append(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                fromfile='a/src/app.html', tofile='b/src/app.html')))
document.write_text(after)
# Prune unsupported routes from the protected build, not just hide menu entries.
allowed = {'+layout.svelte', '+layout.js', '+error.svelte', '(app)/+layout.svelte',
           '(app)/+page.svelte', '(app)/c/[id]/+page.svelte'}
for route in (checkout / 'src/routes').rglob('*'):
    if route.is_file() and str(route.relative_to(checkout / 'src/routes')) not in allowed:
        before = route.read_text()
        changes.append(''.join(difflib.unified_diff(before.splitlines(True), [],
                       fromfile='a/src/routes/' + str(route.relative_to(checkout / 'src/routes')), tofile='/dev/null')))
        route.unlink()
(root / 'patches/open-webui-v0.13.3-iteration3.patch').write_text(
    (root / 'patches/open-webui-v0.13.3-poc.patch').read_text() + ''.join(changes))
# Verify the actual patch (including deleted unsupported routes) against a clean
# checkout; then compare patched files to the exact build inputs.
verification = root / '.build/patch-verification'
if verification.exists():
    shutil.rmtree(verification)
verification.mkdir()
with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
    bundle.extractall(verification, filter='data')
patch = root / 'patches/open-webui-v0.13.3-iteration3.patch'
subprocess.run(['git', 'apply', '--check', str(patch)], cwd=verification, check=True)
subprocess.run(['git', 'apply', str(patch)], cwd=verification, check=True)
for source in (root / 'frontend').rglob('*'):
    if source.is_file():
        relative = source.relative_to(root / 'frontend')
        assert (verification / relative).read_bytes() == (checkout / relative).read_bytes()
assert (verification / 'backend/open_webui/main.py').read_bytes() == (root / 'docker/main.py').read_bytes()
print('Prepared pinned Open WebUI source with protected Svelte routes.')