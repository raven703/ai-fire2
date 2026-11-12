#!/usr/bin/env bash
# Real output-only transport fault. Run sequentially, never alongside other tests.
set -euo pipefail
cd /home/user/ai-fire2
mkdir -p artifacts
sed 's/timeout: 3/timeout: 30/' docker/litellm.yaml > artifacts/native-output-fault-litellm.yaml
cat > artifacts/native-output-fault-compose.yaml <<'EOF'
services:
  litellm:
    volumes:
      - /home/user/ai-fire2/artifacts/native-output-fault-litellm.yaml:/app/config.yaml:ro
EOF
restore() {
  docker compose -f compose.native.yaml start gateway >/dev/null 2>&1
  docker compose -f compose.native.yaml up -d --no-deps litellm >/dev/null 2>&1
}
trap restore EXIT
docker compose -f compose.native.yaml -f artifacts/native-output-fault-compose.yaml up -d --no-deps litellm
sleep 8
docker compose -f compose.native.yaml run --rm --no-deps -T --entrypoint python browser-tests -c 'from pathlib import Path; Path("/artifacts/.output-phase-ready").unlink(missing_ok=True)'
docker compose -f compose.native.yaml run --rm --no-deps -e NATIVE_FAULT_MODE=output-gateway-down browser-tests pytest -q /app/tests/test_native_acceptance.py -k output_transport > artifacts/native-output-outage.log 2>&1 &
task=$!
stopped=0
for i in $(seq 1 45); do
  if test -f artifacts/.output-phase-ready; then
    docker compose -f compose.native.yaml kill -s SIGKILL gateway
    stopped=1
    break
  fi
  sleep 1
done
wait "$task"
test "$stopped" = 1
cat artifacts/native-output-outage.log