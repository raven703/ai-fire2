# GitHub frontend build and WSL pull deployment

## Process

`.github/workflows/build-openwebui.yml` runs on ubuntu-24.04 with Node 22, locked
`npm ci`, upstream v0.13.3 and the ordered patch manifest. `setup-fork.py` supports
mail patches and historical raw diffs. Restored Git tree is checked against the
local fork through artifact provenance; reconstructed commit hashes may differ
because git-am committer timestamps differ. Both admin routes must compile.

Pushes touching patches, manifest or build inputs trigger CI; documentation-only
changes do not. Manual workflow_dispatch is available. Concurrency cancels stale
same-ref runs. Artifacts expire after 14 days; rebuild the exact commit if expired.

From a clean checkout at the desired main commit, execute the absolute script:

```sh
/home/user/ai-fire2/scripts/deploy-github-frontend.sh
```

It selects a successful exact-SHA main run, downloads its named artifact, rejects
unsafe archive paths/symlinks, verifies full file inventory, project SHA, fork tree,
lockfile, patch hashes and Native Python hashes. Existing gh/environment/Git
credentials are used in memory; authorization is stripped on signed-storage
redirects. No inbound WSL connection or credentials in Actions are required.

Local Dockerfile.native-artifact copies the prebuilt adapter-static output; no
Node/npm/Vite command runs in WSL. Native extensions, fork backend and gateway/NLP
build from the same checkout. Auditor operator setting is preserved. Retention
and users reside in existing volumes; deployment never changes their permissions.

Before replacement the script tags old images and copies Compose overlays into
ignored `artifacts/deployment-<UTC>/`. Missing old Docker image blobs use container
rootfs export/import; mounted data is excluded. Build logs and rollback overlay
are retained. Errors after replacement restore previous service images. Health,
anonymous API denial and installed manifest are checked. Browser regression is
still required for release acceptance; health alone is not functional acceptance.

## Verification of initial rollout

CI run 43404210182 built dbfb57539842bac37050cad1b0f1569db8095a9c. Artifact
`openwebui-frontend-dbfb57539842bac37050cad1b0f1569db8095a9c`: 4826 files, all verified.
Later operational changes do not change frontend/fork contents; installed manifest
is the authoritative source SHA. See ignored artifacts/frontend-run.json.

Chromium: status/evidence workflow 1 passed; original Native/OCR/Policy Manager/
delete regression 7 passed. Targeted backend tests: 23 passed. Persistent event
and decrypted evidence digest verified after Native/Vault restart. Synthetic secret
absent from event database, chat history and evidence ciphertext bytes. Quarantine
empty. Existing account permissions unchanged; only a newly created Synthetic CI
Officer receives separate evidence grant. Retention is OFF after acceptance.

OpenBao's prior periodic tokens had expired: lookup/encrypt/renew returned 403.
Existing local recovery quorum generated temporary root solely to reissue split
scoped service tokens; temporary root revoked, no secrets printed. Added internal
`transit-renewer` periodically renews tokens, with healthcheck. It cannot recover
already expired tokens; recovery still requires authorized quorum. Long downtime
beyond token lifetime remains an operational recovery case, never an ALLOW fallback.