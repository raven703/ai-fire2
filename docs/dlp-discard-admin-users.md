# Admin discovery and DLP working-copy deletion

Deployed on Native port 8089. Exact GET paths for upstream users/groups lists
are admitted; upstream authorization remains enforced. User mutations remain
closed. Native profile requests return a fixed local placeholder, never remote
or uploaded profile content.

DLP discard atomically removes only the draft pointer with expected active and
draft revision checks; immutable versions and a discard audit record remain.
Existing admin-only proxy denies auditor mutation. Custom rule removal in UI
also removes associated dictionary/regex from working copy; save and publish
are still required. Built-in categories use explicit disable rather than rule
deletion (unknown detector categories fail closed). History is not an erasure UI.

Verification: policy-store tests 4 passed; Chromium admin discovery, custom rule
removal, discard, unchanged active revision, auditor denial, responsive layout
2 passed in 23.14s. Guarded frontend build passed. Final backend-only image
rebuild reused frontend cache. Native health 200. Starting draft content restored
after browser test; no user deletion or active-policy publication performed.

Evidence: artifacts/dlp-discard-tests.log, dlp-discard-browser.log,
dlp-discard-build-result.log. Fork patch 0013 recorded in manifest.