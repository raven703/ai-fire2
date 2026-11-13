# DLP Status

Original Open WebUI route: `/admin/dlp-status`, beside DLP Policies. Backend uses
upstream verified sessions; administrators and configured `DLP_AUDITOR_IDS` may read.
Ordinary users receive 403 regardless of navigation visibility. Evidence permission
is independent and is never implied by either role.

Schema 1.0 events contain UUID event/correlation IDs, UTC epoch timestamp, actor ID,
chat ID, source, action, safe reason code, policy version/revision, detector findings
and confidence only where provided, generated block/page references, elapsed time,
file SHA-256/size and evidence reference. Tenant is null: no separate tenant model
exists in this deployment. Original filenames are replaced by `protected-upload`.
Rule IDs are revision + category because the existing policy is keyed by category.
No dictionary values, regex patterns, extracted text, matched values or credentials
are written to the event database. Standard events are SIEM-independent; there is
no SIEM transport, SOAR or approval workflow.

`TECHNICAL_FAILURE` is distinct from content-based REVIEW. OCR empty/low-confidence,
parser errors, unsupported content, limits and dependency failures are safe reason
codes, not instructions to approve the file. User messages include an explanation,
reason and event UUID. Internal exceptions are suppressed.

The status page includes counts, daily counts, category counts, latest events,
filters, chronological ordering and 25-row pagination, detail, retention settings
and access audit. Storage is additive in the existing Native data volume.

Limitations: filters currently load content-free event rows before pagination;
large installations need SQL-indexed filtering and event-retention controls.
Category match_count counts detector findings, not unique people. Exact cell-level
mapping is not available. CHAT input events can include repeated admission checks;
they are operations, not unique user turns. Mock outcome is updated for admitted
chat events after completion; NOT_SENT never claims a call happened. General
writer and output safety checks remain mandatory but are not separate status rows.