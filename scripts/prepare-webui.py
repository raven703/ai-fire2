"""Generate upstream entrypoint and reviewable patch without touching vendor files."""
from pathlib import Path
import difflib
import subprocess

root = Path('/home/user/ai-fire2')
commit = 'b0e6098e940942281d9c83f3529ea117287a3a22'
source = subprocess.check_output(['git', '-C', str(root / 'vendor/open-webui'),
                                  'show', f'{commit}:backend/open_webui/main.py']).decode()
updated = source + '\nfrom ai_firewall.webui_poc import protect\napp = protect(app)\n'
(root / 'docker/main.py').write_text(updated)
(root / 'patches/open-webui-v0.13.3-poc.patch').write_text(''.join(difflib.unified_diff(
    source.splitlines(True), updated.splitlines(True),
    fromfile='a/backend/open_webui/main.py', tofile='b/backend/open_webui/main.py')))