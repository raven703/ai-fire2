# Bulk version deletion and history visibility

Deployed on 8089. Deleted version events disappear from the default history;
"Показать удалённые" exposes retained audit records. Per-row checkboxes share
selection by unique version ID, with select-all and selected-count controls.
Active/current-draft/deleted versions cannot be selected. Admin-only batch action
validates all IDs under BEGIN IMMEDIATE before deleting any body or appending
audit records; duplicate/empty/oversized/missing/protected selections fail closed.
Single deletion uses the same atomic primitive. Audit remains unchanged except
for appended deletion events. Unsaved edits block deletion.

Validation: 6 store tests passed including batch all-or-nothing; 3 Chromium tests
passed in 63.26s including disappearance, retained audit toggle, two-version bulk
selection/deletion, publication/rollback, responsive layout and RBAC checks.
Only newly created test versions deleted. Native health 200. Services restored.
Guarded build passed with one-run start-swap allowance 1152 MiB, growth/RAM
watchdog unchanged and no watchdog stop. Persistent build script unchanged.
Evidence: artifacts/dlp-bulk-{unit,browser,build,deploy}.log.