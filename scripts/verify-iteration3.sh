#!/bin/sh
# Reproducible normal + detector-failure + real Gateway-outage phases.
set -eu
cd /home/user/ai-fire2
mkdir -p artifacts
restore() { docker compose up -d gateway >/dev/null; }
trap restore EXIT INT TERM
docker compose up -d
docker compose run --rm --no-deps tests pytest -q -p no:cacheprovider /app/tests
docker compose run --rm --no-deps browser-tests
DETECTOR_FAILURE=1 docker compose up -d gateway
sleep 2
docker compose exec -T gateway python -c 'import httpx,os; r=httpx.post("http://localhost:8000/chat",headers={"Authorization":"Bearer "+os.environ["USER_KEY"]},json={"text":"SYNTHETIC_PII_DETECTOR_FAULT"}); assert r.status_code==503; print("mandatory detector failure: 503")'
restore
docker compose stop gateway
FAULT_MODE=gateway-down docker compose run --rm --no-deps browser-tests
restore
docker compose logs --no-color > artifacts/iteration3-container.log
if grep -q 'SYNTHETIC_PII_' artifacts/iteration3-container.log; then
    echo 'FAIL: raw synthetic canary in container logs'; exit 1
fi
echo 'PASS: no raw synthetic canary in container logs'
docker compose ps