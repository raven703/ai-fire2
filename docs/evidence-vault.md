# Encrypted Evidence Vault v1

## Security model

Retention defaults OFF. An administrator explicitly enables it and selects BLOCK,
REVIEW and optionally technical refusals. Defaults: seven days, 10 MiB per object,
256 MiB ciphertext quota. Settings apply to future objects; disabling retention
does not remove existing objects. No existing volume is removed or migrated away.

Native forwards rejected bytes only to the existing internal Vault v2 service.
That service generates a fresh 256-bit AES-GCM DEK and 96-bit nonce per object.
Existing OpenBao Transit `pii` KEK wraps the DEK using the existing split encrypt /
decrypt credentials. There is no second key-management authority or persisted
plaintext key. This deliberately reuses the KEK and therefore its rotation and
availability domain; separate Transit key segregation is not claimed.

AAD binds evidence/event/user/chat IDs, policy revision, SHA-256, extension, size
and expiry to both the local ciphertext and Transit wrapped key. Tampering causes
decryption refusal. Plain originals exist only in request/process memory and the
existing RAM-backed OCR quarantine. Neither original nor extracted text goes into
the event SQLite, normal file store, rejected chat history or Mock.

Ciphertext, nonce, wrapped key and immutable envelope metadata are atomically
committed in `/evidence/ciphertext.db` on new `evidence-ciphertext` volume. Envelope
metadata is logically separate columns, not a plaintext document. Event metadata
is in the existing Native volume. PENDING precedes encryption; only acknowledged
commit becomes STORED. Failures remain FAILED, never permit admission. A crash
after vault commit but before event acknowledgement can leave an unreferenced
encrypted object; it expires normally. PENDING is never presented as STORED.

## Access and lifecycle

`DLP_EVIDENCE_VIEW` is an explicit user-ID grant in the Native permissions table,
not automatically assigned to admins/auditors. Every issuance rechecks the grant,
event binding and TTL; ATTEMPT / DENIED / SUCCESS / FAILED are audited without
content. Internal decryption attempts are also audited by Vault. Local provisioning
must verify the exact intended account ID before inserting a grant.

UI button «Просмотреть оригинал» uses controlled attachment download, not an active
PDF/OOXML iframe. Explicit warning describes sensitive/active content and recipient
copying. `no-store`, nosniff and sandbox headers; temporary blob URL revoked after
issuance; no localStorage/sessionStorage content or chat insertion. Download cannot
be revoked after delivery; authorized recipients can save/copy bytes. This is not
a sanitized PDF viewer or a DRM mechanism. Use an isolated local application.

The synchronous request is bounded by service timeouts; no reusable public signed
URL or plaintext server cache exists. A 60-second Native cleanup task and all vault
store/read operations purge expired envelopes and audit TTL_DELETE. Expired event
references become EXPIRED; the event itself remains content-free for audit. SQLite
secure_delete is enabled; this does not guarantee physical erasure from snapshots.
Deletion removes wrapped keys with ciphertext, not the shared Transit KEK.

## Verification

Unit tests cover unique DEKs, roundtrip, ciphertext/metadata tampering, wrong event,
TTL, quotas, safe defaults and permission separation. Live Transit roundtrip was
executed. Browser and deployment results are recorded in ignored artifacts logs;
do not treat tests merely added to source as executed acceptance.