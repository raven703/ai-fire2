CREATE TABLE IF NOT EXISTS mappings (
 token text PRIMARY KEY,
 scope text NOT NULL,
 lookup text NOT NULL,
 ciphertext text NOT NULL,
 expires bigint NOT NULL,
 UNIQUE(scope,lookup)
);
CREATE INDEX IF NOT EXISTS mappings_expiry ON mappings(expires);