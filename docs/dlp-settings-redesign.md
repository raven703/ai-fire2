# Readable DLP settings

Deployed redesigned original Open WebUI `/admin/dlp` on port 8089.

- Russian category names, explicit action explanations and confidence guidance.
- Active revision, saved draft and RBAC status cards; searchable categories.
- Separate corporate dictionaries and advanced regex/JSON section.
- Unsaved-change indicator; publication disabled until draft is saved.
- Explicit rollback confirmation; readable feedback for errors/success.
- Responsive layout, dark theme and keyboard focus states.
- Backend policy logic, mandatory inspection, reveal permissions unchanged.

Validation:
- Guarded native build exit 0, watchdog_stop=False.
- Chromium layout/admin/auditor/search/unsaved/mobile test: 1 passed, 12.59s.
- Chromium draft/publish/BLOCK/rollback/REVIEW/RBAC regression: 1 passed, 40.21s.
- Regression restores starting active policy in finally; no real chat data used.
- Host 8089 health 200. Temporarily stopped containers restarted.
- Fork provenance check passed. Fork patch recorded as 0012 in manifest.

Local evidence: artifacts/dlp-ui-layout.log, dlp-ui-policy-regression.log,
dlp-settings-desktop.png, dlp-settings-dark.png, dlp-settings-mobile.png.
Screenshots show the current viewport within the independently scrolling page.
Existing frontend build warnings (including self-closing textarea markup) do not
prevent compilation; no browser page errors occurred in the layout test.