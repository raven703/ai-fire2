#!/usr/bin/env bash
# Pull deployment only: never runs npm/Vite and never removes volumes.
set -Eeuo pipefail
cd "$(dirname "$(realpath "$0")")/.."
exec 9>/tmp/ai-fire2-deploy.lock
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
sha=$(git rev-parse "${1:-HEAD}^{commit}")
[[ "$sha" == "$(git rev-parse HEAD)" ]] || { echo 'Checkout requested commit first'; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Main working tree must be clean'; exit 1; }
[[ -z "$(git -C forks/open-webui status --porcelain)" ]] || { echo 'Fork must be clean'; exit 1; }
python3 scripts/check-fork.py
mkdir -p artifacts
python3 - "$sha" <<'PY'
import importlib.util,json,sys,zipfile,shutil,stat
from pathlib import Path
spec=importlib.util.spec_from_file_location('api','scripts/github-api.py');api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
sha=sys.argv[1];repo='repos/raven703/ai-fire2/'
runs=api.request(repo+'actions/workflows/build-openwebui.yml/runs?head_sha='+sha+'&status=success&per_page=20')['workflow_runs']
runs=[r for r in runs if r['head_sha']==sha and r['head_branch']=='main' and r['conclusion']=='success']
if not runs:raise SystemExit('No successful frontend run for exact SHA')
run=runs[0];items=api.request(repo+'actions/runs/'+str(run['id'])+'/artifacts')['artifacts']
artifact=next(a for a in items if a['name']=='openwebui-frontend-'+sha and not a['expired'])
archive=Path('artifacts/frontend-download.zip');archive.write_bytes(api.request(repo+'actions/artifacts/'+str(artifact['id'])+'/zip',binary=True))
stage=Path('artifacts/frontend-stage');shutil.rmtree(stage,ignore_errors=True);stage.mkdir()
with zipfile.ZipFile(archive) as z:
    if sum(i.file_size for i in z.infolist())>2_000_000_000:raise ValueError('artifact_too_large')
    for i in z.infolist():
        p=Path(i.filename)
        if p.is_absolute() or '..' in p.parts or stat.S_ISLNK(i.external_attr>>16):raise ValueError('unsafe_archive')
    z.extractall(stage)
Path('artifacts/frontend-run.json').write_text(json.dumps({'run_id':run['id'],'url':run['html_url'],'sha':sha,'artifact':artifact['name']},indent=2))
print(run['html_url'],artifact['name'])
PY
python3 scripts/frontend-artifact.py verify artifacts/frontend-stage
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="artifacts/deployment-$stamp"
mkdir -m 700 "$backup"
services=(webui gateway pii)
containers=(ai-fire2-native-webui-1 ai-fire2-native-gateway-1 ai-fire2-native-pii-1)
for i in "${!services[@]}"; do
  current=$(docker inspect "${containers[$i]}" --format '{{.Image}}')
  target="ai-fire2-rollback:${services[$i]}-$stamp"
  if docker image inspect "$current" >/dev/null 2>&1; then
    docker image tag "$current" "$target"
  else
    # A previous build may have replaced an image tag while the old container ran.
    # Commit its root filesystem; mounted persistent data is deliberately excluded.
    if ! docker commit "${containers[$i]}" "$target" > "$backup/${services[$i]}-snapshot.log"; then
      docker export "${containers[$i]}" -o "$backup/${services[$i]}-rootfs.tar"
      # Imported roots need the original service command (Compose restores env/mounts).
      case "${services[$i]}" in
        gateway) command='["python","-m","ai_firewall.services"]' ;;
        pii) command='["uvicorn","ai_firewall.pii_service:app","--host","0.0.0.0","--port","8000","--no-access-log","--log-level","critical"]' ;;
        webui) command='["uvicorn","ai_firewall.native_runtime:app","--host","0.0.0.0","--port","8080","--no-access-log"]' ;;
      esac
      docker import --change 'ENV PYTHONPATH=/app/src' --change 'WORKDIR /app' --change "CMD $command" "$backup/${services[$i]}-rootfs.tar" "$target"
    fi
  fi
done
# Keep existing auditor configuration; never infer permissions from a new shell env.
export DLP_AUDITOR_IDS
DLP_AUDITOR_IDS=$(docker inspect ai-fire2-native-webui-1 --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^DLP_AUDITOR_IDS=//p')
cp compose.native.yaml compose.native-core.yaml compose.pii-test.yaml compose.native-vault-v2.yaml compose.file-dlp.yaml "$backup/"
printf 'services:\n  webui:\n    image: ai-fire2-rollback:webui-%s\n  gateway:\n    image: ai-fire2-rollback:gateway-%s\n  pii:\n    image: ai-fire2-rollback:pii-%s\n' "$stamp" "$stamp" "$stamp" > "$backup/rollback.yaml"
compose=(docker compose -f compose.native.yaml -f compose.native-core.yaml -f compose.pii-test.yaml -f compose.native-vault-v2.yaml -f compose.file-dlp.yaml)
changed=false
rollback(){
  code=$?
  if $changed; then
    echo 'Deployment failed; restoring previous images (volumes retained)' >&2
    "${compose[@]}" -f "$backup/rollback.yaml" up -d --no-build --no-deps webui gateway pii || true
  fi
  exit "$code"
}
trap rollback ERR
docker build -f docker/Dockerfile.native-artifact -t "ai-fire2-native:ci-$sha" . > "$backup/native-build.log" 2>&1
"${compose[@]}" build gateway pii > "$backup/services-build.log" 2>&1
docker tag "ai-fire2-native:ci-$sha" ai-fire2-native:source
changed=true
"${compose[@]}" up -d --no-build --no-deps gateway pii webui
for attempt in $(seq 1 90); do
  if curl --silent --fail http://127.0.0.1:8089/health >/dev/null; then break; fi
  sleep 2
done
curl --silent --fail http://127.0.0.1:8089/health >/dev/null
# Authenticated endpoints must not become anonymous after deployment.
python3 - <<'PY'
import urllib.request,urllib.error
for path in ('/api/v1/dlp/status','/api/models/native'):
    try:urllib.request.urlopen('http://127.0.0.1:8089'+path);raise RuntimeError('anonymous_endpoint_open')
    except urllib.error.HTTPError as e:assert e.code in (401,403),e.code
print('Native health and authentication boundary PASS')
PY
docker exec ai-fire2-native-webui-1 python -c "import json;d=json.load(open('/app/frontend-build-manifest.json'));assert d['project_sha']=='$sha';print('Installed frontend:',d['project_sha'])"
trap - ERR
echo "DEPLOYED $sha; rollback images/configuration: $backup"