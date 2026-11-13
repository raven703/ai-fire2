# Dedicated deletion permit

DELETE no longer uses text DLP admission. Authenticated backend sends a strict
content-free manifest to Gateway `/native/delete-permit`. Manifest binds user,
chat, current revision, exact table/row IDs and original-row SHA-256. Gateway
signs operation `chat-delete`; existing nonce consumption, ORM exact snapshot
comparison, transaction, guard_flush and SQLite triggers remain unchanged.
Guard explicitly rejects INSERT/UPDATE under a deletion permit. Ownership and
revision locking remain in the original delete route. No raw content sent.

The previous letters-only hash workaround is removed. Digests are standard hex.
Actual historical failing chat was not identified or deleted; its exact failing
category is NOT established. Numeric hashes entering text detectors and custom
rules matching metadata were plausible causes, not proven historical evidence.

Checks executed: 12 targeted tests passed (manifest scope/digest/content/update/
duplicate rejection, existing permit/ORM protections); existing original-UI
preview/delete/group-delete Chromium scenario passed in 19.10s. Native/Gateway
rebuilt and deployed. Long-history/custom-policy/foreign-owner end-to-end matrix
and targeted replay/tamper tests specifically for the new endpoint remain to be
expanded; no claim that every requested adversarial case was executed.
No user chat was manually deleted, no SQLite rows manually modified.