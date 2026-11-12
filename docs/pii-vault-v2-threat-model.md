# Vault v2 threat model and design

Synthetic-only acceptance environment. Assets: originals, mapping ownership,
AEAD/HMAC keys, reveal authorization, recovery material. Threats include database
dump theft, ciphertext/token swapping, guessed tokens, foreign-user/chat access,
expired mappings, dependency outages and plaintext persistence in UI/history.
Host/root compromise, process-memory inspection and malicious trusted Gateway
are not resisted. Display necessarily exposes originals in browser RAM/DOM.

Use OpenBao Transit aes256-gcm96 with random nonces, non-exportable encryption
key, separate HMAC key, contextual AAD containing tenant/user/chat/token/expiry.
No convergent encryption. PostgreSQL stores ciphertext and keyed lookup only.
Token is 256 random bits. Scope and value HMAC gives stable reuse until expiry;
HMAC key rotation requires explicit migration, unlike encryption-key rewrap.
Only trusted Gateway may submit full-batch final MASK authorization. Reveal has
separate credentials, ownership checks and no-cache response; no original writes
to WebUI, no replacement in stored history/model context. Failures deny access.

Backup must cover PostgreSQL and sealed OpenBao storage plus separately held
unseal shares. Never commit tokens/unseal material. Rotation uses Transit rotate
and rewrap; old key versions retained until restore tests and backup expiry.
Deletion removes active mappings; backups retain encrypted data until expiry.
Logs contain operation outcome only, never request bodies or exception payloads.

References: OpenBao official Transit API and TCP listener documentation reviewed
November 12, 2026. TLS required outside an explicitly isolated local test network.
Implementation and executed acceptance results tracked separately; this document
is a design, not a claim that recovery or security tests passed.