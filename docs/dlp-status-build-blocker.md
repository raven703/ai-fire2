# Deployment blocker — 2026-11-12

Implementation is NOT accepted or deployed as a complete feature.

WSL exposes 9948 MiB RAM. All previously running auxiliary PoC, acceptance and
Native heavy services were temporarily stopped for sequential guarded builds.
Frontend attempts with 6144/4608/5120 MiB heaps crossed the 1024 MiB available-RAM
safety floor during Rollup chunk rendering. 3072 and 4096 MiB attempts failed with
Node fatal heap exhaustion. A 5120 MiB attempt with 4 MiB semi-space also crossed
the floor. Watchdog was retained. No global cleanup, volume removal, host swap
changes or unguarded build was used. Persistent build script is unchanged.

All temporarily stopped containers were started again. Existing Native frontend,
gateway and NLP containers retain the prior deployment. Vault v2 alone was rebuilt
and recreated with additive evidence endpoints and a new empty ciphertext volume;
existing persistent data/credentials and Transit configuration were preserved.
Retention was never enabled, permissions were not granted, and browser acceptance
was not run. A synthetic internal envelope roundtrip was performed successfully.

Verified: 23 targeted tests passed (one dependency deprecation warning), Python
compileall and git diff checks passed. Tests were run in the regression image with
cryptography 48.0.1 installed ephemerally. Chromium test added but NOT executed.

Remaining required work: obtain a safe build environment with sufficient RAM or
reduce bundler peak memory without weakening runtime isolation; build/redeploy
Native + gateway + NLP; explicitly grant the intended admin account (two admin
identities exist, so choose deliberately); enable retention through admin settings;
run full synthetic format matrix, failure/restart checks and Chromium acceptance.
Current controlled original issuance is download-only; a sanitized PDF/image
viewer, if required instead of controlled issuance, remains additional work.

Known review items before acceptance: SQL indexed event filtering, full technical
reason mapping including policy conflicts and outer upload-size refusal; precise
Mock outcome/event linkage rather than chat-wide update; generated sheet identifiers;
stronger cross-database reconciliation beyond PENDING failure and orphan TTL.

Evidence logs: artifacts/evidence-targeted.log, evidence-vault-build.log,
evidence-services-build.log, evidence-native-build-result.log,
native-build-6144-controlled.log and native-build-6144-memory.csv. Build logs are
overwritten per attempt; final attempt records resource-pressure stop.