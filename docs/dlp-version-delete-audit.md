# Archived version deletion with retained audit

Deployed on Native 8089. Admin can irreversibly delete archived version bodies.
BEGIN IMMEDIATE serializes deletion with publication/discard; expected active
revision and all state pointers are checked. Active version and current draft
cannot be deleted. Audit rows are never deleted; delete_version records actor,
timestamp, version ID and original digest in the same transaction. Restoring a
deleted version fails. View marks every related audit event unavailable.

UI asks for confirmation, disables deletion for protected/deleted versions and
auditors, and prevents refresh from dropping unsaved edits during deletion.
Audit defaults collapsed and has explicit show/hide controls; at most the latest
100 events are displayed (existing limit). Multiple events may reference one
version; deleting it affects restoration for all those events.

Evidence: 5 policy-store tests passed; 3 Chromium tests passed in 59.79s covering
version deletion/cancellation, audit retention, protected pointers, auditor denial,
collapse/expand, layout and publication/rollback regression. Only a newly created
synthetic archived revision was deleted. No pre-existing user version deleted.
Build exit 0, watchdog_stop=False. This run used an in-memory start-swap ceiling
1088 MiB instead of 1024; script unchanged, RAM/growth watchdog retained. Services
restored, changed webui/pii deployed, health 200. Logs: artifacts/dlp-version-delete-*.