-- Phase 2d — KR Crypto backfill SQL
--
-- Permanent location on Oracle:
--   /home/ubuntu/x402watch/migrations/v21_attribution_backfill.sql
--
-- Apply order:
--   1. Schema additions (transactions.attribution_source + supporting tables)
--   2. Backup table (full, untouched copy of transactions)
--   3. KR Crypto seller — staging table built from merchant feed ingestion
--      OR from KR Crypto's stats.jsonl directly (uploaded as a temp CSV)
--   4. UPDATE transactions for tx_hashes that exist on both sides
--   5. Verification queries
--   6. (optional) Re-aggregate services + run derive_global
--
-- NEVER hard-deletes a row. Worst-case rollback: TRUNCATE transactions then
-- INSERT * FROM transactions_pre_v21_backup. The schema additions are
-- additive — no destructive ALTER.
--
-- Apply with:
--   sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch \
--     -f /home/ubuntu/x402watch/migrations/v21_attribution_backfill.sql

BEGIN;

-- ─── 1. Schema additions (idempotent) ────────────────────────────────
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS attribution_source TEXT,
    ADD COLUMN IF NOT EXISTS feed_merchant_id   TEXT,
    ADD COLUMN IF NOT EXISTS is_x402_payment    BOOLEAN;

CREATE INDEX IF NOT EXISTS transactions_attribution_idx
    ON transactions (attribution_source, time DESC);

-- Merchant feed registry — see merchant_feed_spec.md §3
CREATE TABLE IF NOT EXISTS merchant_feed_keys (
    merchant_id      TEXT NOT NULL,
    key_id           TEXT NOT NULL,
    public_key_b64url TEXT NOT NULL,
    feed_base_url    TEXT,
    valid_from       TIMESTAMPTZ NOT NULL,
    valid_until      TIMESTAMPTZ NOT NULL,
    registered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at       TIMESTAMPTZ,
    PRIMARY KEY (merchant_id, key_id)
);

CREATE TABLE IF NOT EXISTS merchant_feed_state (
    merchant_id    TEXT PRIMARY KEY,
    last_feed_seq  BIGINT NOT NULL,
    last_fetch_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── 2. Backup table — full snapshot, NEVER modified by anything below
CREATE TABLE IF NOT EXISTS transactions_pre_v21_backup AS
SELECT * FROM transactions WHERE FALSE;       -- structure-only first

INSERT INTO transactions_pre_v21_backup
    SELECT * FROM transactions
    ON CONFLICT DO NOTHING;                   -- second invocation = no-op

-- ─── 3. Mark all pre-existing rows as legacy_collapse ────────────────
UPDATE transactions
    SET attribution_source = 'legacy_collapse'
WHERE attribution_source IS NULL;

-- ─── 4. KR Crypto staging table (loaded from stats.jsonl externally) ─
-- Operator loads stats.jsonl into this table via a one-off COPY, e.g.:
--
--   psql -c "TRUNCATE kr_crypto_settlements_staging;"
--   cat /home/ubuntu/KRCryptoAPI/stats.jsonl \
--     | jq -c 'select((.kind // .event) == "payment_settled")
--               | {tx_hash: (.transaction // .tx_hash),
--                  chain: (.network // .chain),
--                  resource_url: (
--                    if (.endpoint // "")|startswith("http") then (.endpoint)
--                    elif (.endpoint // "")|startswith("/") then "https://api.printmoneylab.com" + (.endpoint)
--                    else "https://api.printmoneylab.com/api/v1/" + (.endpoint)
--                    end
--                  ),
--                  payer: (.payer // .buyer),
--                  price_usd: .price_usd,
--                  settled_at: (.ts // .settled_at)}' \
--     | psql -U x402watch -d x402watch -c "COPY kr_crypto_settlements_staging FROM STDIN WITH (FORMAT csv, ...);"
--
-- For simplicity, we use a JSON-shaped temp table.

CREATE TABLE IF NOT EXISTS kr_crypto_settlements_staging (
    tx_hash      TEXT NOT NULL,
    chain        TEXT NOT NULL,
    resource_url TEXT NOT NULL,
    payer        TEXT,
    price_usd    NUMERIC(12,6),
    settled_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tx_hash, chain)
);

-- Verify staging has data before proceeding.
DO $$
DECLARE
    n_staging INT;
BEGIN
    SELECT COUNT(*) INTO n_staging FROM kr_crypto_settlements_staging;
    IF n_staging = 0 THEN
        RAISE EXCEPTION 'kr_crypto_settlements_staging is empty — load stats.jsonl first (see comments above)';
    END IF;
    RAISE NOTICE 'kr_crypto_settlements_staging row count: %', n_staging;
END $$;

-- ─── 5. Resolve each settlement to a services.id ─────────────────────
-- A settlement is bound to the services row with the matching resource_url.
-- We require seller_address match against KR Crypto's wallet too, as
-- a defence-in-depth check.

CREATE TEMP TABLE kr_crypto_resolved AS
SELECT
    st.tx_hash,
    LOWER(REPLACE(st.chain, 'eip155:8453', 'base')) AS chain_norm,
    s.id   AS service_id,
    s.seller_address,
    st.payer,
    st.price_usd,
    st.settled_at
FROM kr_crypto_settlements_staging st
JOIN services s
  ON s.resource_url = st.resource_url
 AND (
   (st.chain LIKE 'eip155:%' AND LOWER(s.seller_address) = LOWER('0xcF9223eCe895258dEa8D288AEBcf846Ab8E342fB'))
   OR
   (st.chain LIKE 'solana:%' AND s.seller_address = '3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9')
 );

SELECT
    COUNT(*) AS staged_settlements,
    COUNT(DISTINCT service_id) AS distinct_services,
    MIN(settled_at) AS earliest,
    MAX(settled_at) AS latest
FROM kr_crypto_resolved;

-- ─── 6. UPDATE transactions for tx_hashes that exist on both sides ───
-- Strict join on (tx_hash, chain). Updates service_id + attribution_source
-- in place. is_x402_payment flipped to TRUE.
WITH updated AS (
    UPDATE transactions t
       SET service_id        = r.service_id,
           attribution_source = 'merchant_feed:kr-crypto',
           feed_merchant_id   = 'kr-crypto',
           is_x402_payment    = TRUE
      FROM kr_crypto_resolved r
     WHERE t.tx_hash = r.tx_hash
       AND (t.chain = r.chain_norm OR (r.chain_norm = 'base' AND t.chain = 'base'))
    RETURNING t.tx_hash
)
SELECT COUNT(*) AS updated_rows FROM updated;

-- ─── 7. INSERT any settlements that x402watch never observed ─────────
-- These are settlements KR Crypto saw but the indexer missed entirely
-- (e.g. Solana, where indexer/solana.py is broken). Insert with the
-- correct attribution from the start.
INSERT INTO transactions (
    tx_hash, chain, time, buyer_address, seller_address, service_id,
    amount, attribution_source, feed_merchant_id, is_x402_payment
)
SELECT
    r.tx_hash,
    r.chain_norm,
    r.settled_at,
    r.payer,
    r.seller_address,
    r.service_id,
    r.price_usd,
    'merchant_feed:kr-crypto',
    'kr-crypto',
    TRUE
FROM kr_crypto_resolved r
LEFT JOIN transactions t USING (tx_hash, chain)
WHERE t.tx_hash IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM transactions t2
     WHERE t2.tx_hash = r.tx_hash AND t2.chain = r.chain_norm
  )
ON CONFLICT (tx_hash, chain) DO NOTHING;

-- ─── 8. Mark remaining seller-0xcF92 rows as 'legacy_unmatched' ──────
-- Rows that look like they came from KR Crypto's seller but weren't in
-- the merchant feed are likely non-x402 USDC transfers (CEX deposits,
-- ad-hoc sends). Mark them so they're excluded from x402 traffic stats
-- without being deleted.
UPDATE transactions
   SET attribution_source = 'legacy_unmatched',
       is_x402_payment = FALSE
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
   AND attribution_source = 'legacy_collapse';

-- ─── 9. Verification queries (read-only) ─────────────────────────────
SELECT 'attribution_source distribution after backfill' AS section;
SELECT attribution_source, COUNT(*) AS n
  FROM transactions
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
 GROUP BY 1
 ORDER BY n DESC;

SELECT 'service_id distribution for KR Crypto after backfill' AS section;
SELECT service_id, COUNT(*) AS n, SUM(amount) AS usdc
  FROM transactions
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
   AND is_x402_payment = TRUE
 GROUP BY 1
 ORDER BY n DESC;

-- Expected: rows on 14391 (kr-prices, the majority) + meaningful
-- counts on 14744 (arbitrage-scanner), 14741 (kr-sentiment), and
-- the other 8 KR Crypto endpoints. legacy_unmatched count should
-- equal "x402watch indexed - KR Crypto stats.jsonl" delta (~1,109
-- non-x402 transfers).

COMMIT;

-- ─── 10. Trigger downstream re-aggregation ───────────────────────────
-- (run separately after this transaction commits)
--
--   cd /home/ubuntu/x402watch
--   venv/bin/python -m indexer.derive_global
--
-- This re-computes services.tx_total / volume / real_volume_pct / wash_pct
-- and buyer_seller_labels for KR Crypto's 11 endpoints.

-- ─── 11. Rollback procedure ──────────────────────────────────────────
-- If anything looks wrong post-backfill:
--
--   BEGIN;
--   TRUNCATE transactions;
--   INSERT INTO transactions SELECT * FROM transactions_pre_v21_backup;
--   ALTER TABLE transactions
--     DROP COLUMN attribution_source,
--     DROP COLUMN feed_merchant_id,
--     DROP COLUMN is_x402_payment;
--   COMMIT;
--
-- The backup table is preserved indefinitely until manually dropped.
