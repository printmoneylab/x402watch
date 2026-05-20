-- Option A backfill — re-attribute non-KR multi-seller history
--
-- Permanent location on Oracle:
--   /home/ubuntu/x402watch/migrations/v21_backfill_other_sellers.sql
--
-- Phase 2b P4 fixed NEW transactions for every multi-endpoint seller:
-- the indexer now keys attribution on (seller, chain, price). This file
-- applies the SAME (seller, chain, price) → MIN(id) mapping to the
-- ~799k OLD `legacy_collapse` rows so historical data stops pointing
-- at the seller's MIN(id) service.
--
-- KR Crypto is excluded — it is already exact via the merchant feed
-- (attribution_source = 'merchant_feed:kr-crypto' / 'legacy_unmatched',
-- so its rows are not 'legacy_collapse' anyway; the seller filter is
-- belt-and-suspenders).
--
-- Match logic is byte-for-byte the same as P4's load_seller_map:
--   amount_micro = ROUND(price_amount * 1e6)        -- services side
--   ROUND(transactions.amount * 1e6)                -- tx side (dollar float)
--   GROUP BY LOWER(seller_address), chain, amount_micro  → MIN(id)
-- A transaction whose amount is not exactly a registered price (a
-- fee-included amount like 0.001125, or an endpoint whose price was
-- since changed/removed) matches nothing and stays 'legacy_collapse'
-- — never wrongly bucketed.
--
-- LIMITS (state plainly):
--  * Same-price collision: a seller with N endpoints at one price
--    still collapses to MIN(id) within that price bucket. Section 5
--    measures how many rows that affects.
--  * No ground truth: unlike KR Crypto's merchant feed, there is no
--    way here to tell a real x402 payment from a non-x402 USDC
--    transfer that happens to equal a registered price. is_x402_payment
--    is therefore left untouched (NULL) on backfilled rows.
--
-- SAFETY: transactions_pre_v21_backup (made by backfill_kr_crypto.sql
-- §2) is the rollback source. This file never deletes. Run the DRY RUN
-- (section 2) and read its counts before running section 3.
--
-- Apply:
--   sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch \
--     -v ON_ERROR_STOP=1 -f .../v21_backfill_other_sellers.sql
--   (or copy section by section)

\set kr_evm   '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
\set kr_sol   '3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9'


-- ─── 0. Pre-flight — the backup MUST exist ──────────────────────────
DO $$
DECLARE n BIGINT;
BEGIN
    SELECT COUNT(*) INTO n FROM information_schema.tables
     WHERE table_name = 'transactions_pre_v21_backup';
    IF n = 0 THEN
        RAISE EXCEPTION 'transactions_pre_v21_backup missing — run backfill_kr_crypto.sql section 2 first';
    END IF;
    RAISE NOTICE 'backup table present — rollback is available';
END $$;


-- ─── 1. BEFORE snapshot ─────────────────────────────────────────────
SELECT 'BEFORE — legacy_collapse rows by seller (top 20)' AS section;
SELECT seller_address,
       COUNT(*)                       AS legacy_rows,
       COUNT(DISTINCT service_id)      AS endpoints_now
FROM transactions
WHERE attribution_source = 'legacy_collapse'
  AND LOWER(seller_address) <> :'kr_evm'
  AND seller_address       <> :'kr_sol'
GROUP BY seller_address
ORDER BY legacy_rows DESC
LIMIT 20;
-- Expected: each seller endpoints_now = 1 (the collapse).


-- ─── 2. DRY RUN — preview the re-attribution, write nothing ─────────
-- The mapping CTE mirrors P4 load_seller_map exactly, EXCEPT it omits
-- NULL-price services (`WHERE price_amount IS NOT NULL`). P4's runtime
-- indexer has an (addr, None) fallback for those; the backfill
-- deliberately does not — sending an unmatched historical payment to
-- a price-less service would be a guess, so such rows are left
-- 'legacy_collapse' instead. NULL-price services are rare.
SELECT 'DRY RUN — re-attribution preview' AS section;
WITH seller_price_map AS (
    SELECT LOWER(seller_address) AS addr, chain,
           ROUND(price_amount * 1000000)::bigint AS amount_micro,
           MIN(id) AS service_id
    FROM services WHERE price_amount IS NOT NULL
    GROUP BY LOWER(seller_address), chain, ROUND(price_amount * 1000000)
),
total AS (
    SELECT COUNT(*) AS legacy_total
    FROM transactions
    WHERE attribution_source = 'legacy_collapse'
      AND LOWER(seller_address) <> :'kr_evm'
      AND seller_address <> :'kr_sol'
),
matched AS (
    SELECT COUNT(*) AS will_match,
           COUNT(*) FILTER (WHERE t.service_id IS DISTINCT FROM spm.service_id) AS will_change
    FROM transactions t
    JOIN seller_price_map spm
      ON spm.addr = LOWER(t.seller_address)
     AND spm.chain = t.chain
     AND spm.amount_micro = ROUND(t.amount * 1000000)
    WHERE t.attribution_source = 'legacy_collapse'
      AND LOWER(t.seller_address) <> :'kr_evm'
      AND t.seller_address <> :'kr_sol'
)
SELECT total.legacy_total,
       matched.will_match,
       matched.will_change,
       (total.legacy_total - matched.will_match) AS will_stay_unmatched
FROM total, matched;
-- legacy_total          : non-KR legacy_collapse rows in scope
-- will_match            : rows that find a (seller,chain,price) service
-- will_change           : of those, rows whose service_id actually moves
-- will_stay_unmatched   : no price match (fee-included / removed price)
--                         → stay 'legacy_collapse', re-runnable later


-- ─── 3. APPLY — UPDATE matched rows ─────────────────────────────────
-- Wrapped in a transaction. On a hypertable this UPDATE touches every
-- chunk holding legacy_collapse rows; expect a few minutes for ~799k.
-- Run in a low-traffic window.
BEGIN;

WITH seller_price_map AS (
    SELECT LOWER(seller_address) AS addr, chain,
           ROUND(price_amount * 1000000)::bigint AS amount_micro,
           MIN(id) AS service_id
    FROM services WHERE price_amount IS NOT NULL
    GROUP BY LOWER(seller_address), chain, ROUND(price_amount * 1000000)
)
UPDATE transactions t
   SET service_id         = spm.service_id,
       attribution_source = 'price_match_backfill'
FROM seller_price_map spm
WHERE t.attribution_source   = 'legacy_collapse'
  AND LOWER(t.seller_address) = spm.addr
  AND t.chain                = spm.chain
  AND ROUND(t.amount * 1000000) = spm.amount_micro
  AND LOWER(t.seller_address) <> :'kr_evm'
  AND t.seller_address        <> :'kr_sol';

COMMIT;


-- ─── 4. AFTER snapshot ──────────────────────────────────────────────
SELECT 'AFTER — attribution_source distribution' AS section;
SELECT attribution_source, COUNT(*) AS n
FROM transactions
GROUP BY attribution_source
ORDER BY n DESC;

SELECT 'AFTER — endpoint spread per seller (top 20, x402-attributed)' AS section;
SELECT seller_address,
       COUNT(*)                  AS rows,
       COUNT(DISTINCT service_id) AS endpoints
FROM transactions
WHERE attribution_source = 'price_match_backfill'
GROUP BY seller_address
ORDER BY rows DESC
LIMIT 20;
-- Expected: multi-endpoint sellers now show endpoints > 1.


-- ─── 5. LIMIT measurement — residual same-price collisions ──────────
SELECT 'RESIDUAL — sellers with >1 endpoint at one (chain, price)' AS section;
SELECT addr, chain, amount_micro, n_endpoints
FROM (
    SELECT LOWER(seller_address) AS addr, chain,
           ROUND(price_amount * 1000000)::bigint AS amount_micro,
           COUNT(*) AS n_endpoints
    FROM services
    WHERE price_amount IS NOT NULL
    GROUP BY LOWER(seller_address), chain, ROUND(price_amount * 1000000)
) g
WHERE n_endpoints > 1
ORDER BY n_endpoints DESC
LIMIT 30;
-- These (seller, chain, price) buckets still collapse to MIN(id) —
-- the price-based method cannot split them. Only a merchant feed can.

SELECT 'RESIDUAL — rows still legacy_collapse after backfill (non-KR)' AS section;
SELECT COUNT(*) AS still_legacy_collapse
FROM transactions
WHERE attribution_source = 'legacy_collapse'
  AND LOWER(seller_address) <> :'kr_evm'
  AND seller_address       <> :'kr_sol';
-- Rows with no exact price match: fee-included amounts, prices changed
-- since the payment, or services rows since deleted. Left as
-- 'legacy_collapse' so a future re-run (after services is corrected)
-- can still pick them up.


-- ─── 6. derive_global — run in a shell, NOT in psql ─────────────────
--   cd /home/ubuntu/x402watch && venv/bin/python -m indexer.derive_global
-- Re-aggregates services.tx_total / volume / real_volume_pct /
-- wash_pct + buyer_seller_labels from the corrected service_ids.


-- ─── 7. ROLLBACK (Option A only — keeps KR Crypto + schema) ─────────
-- Restores just the rows this file changed:
--
--   BEGIN;
--   UPDATE transactions t
--      SET service_id         = b.service_id,
--          attribution_source = 'legacy_collapse'
--   FROM transactions_pre_v21_backup b
--   WHERE t.tx_hash = b.tx_hash AND t.chain = b.chain
--     AND t.attribution_source = 'price_match_backfill';
--   COMMIT;
--
-- Full rollback (everything to the pre-v2.1 snapshot) is in
-- backfill_kr_crypto.sql's ROLLBACK section.
