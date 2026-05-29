-- cleanup_duplicate_transactions.sql
--
-- Revenue double-count cleanup. The merchant_feed indexer used to
-- INSERT a duplicate row keyed by CAIP-2 chain (eip155:8453 /
-- solana:<base58>) when a readable-chain row (base / solana / …)
-- already existed for the same tx_hash. This script promotes the
-- duplicate row's attribution data onto the matching readable-chain
-- row, then deletes the CAIP-2 duplicates so the 36 stat-SQL sites
-- (no chain filter) stop double-counting revenue.
--
-- The normalize_chain_merchant_feed.py patch MUST be applied first —
-- otherwise the next merchant_feed run re-creates the duplicates.
--
-- Safe to dry-run (the whole script is wrapped in BEGIN/COMMIT; just
-- swap the final COMMIT for ROLLBACK):
--
--   sed 's/^COMMIT;$/ROLLBACK;/' cleanup_duplicate_transactions.sql \
--     | sudo docker exec -i x402watch-postgres \
--           psql -U x402watch -d x402watch
--
-- Apply:
--
--   sudo docker exec -i x402watch-postgres \
--     psql -U x402watch -d x402watch \
--     -f /tmp/cleanup_duplicate_transactions.sql
--
-- Idempotent: once applied, no rows match the CAIP-2 / solana:<addr>
-- prefix pattern, so a re-run UPDATEs nothing and DELETEs nothing.
-- The safety guard fires only when duplicates remain.

\set ON_ERROR_STOP on

BEGIN;

\echo ''
\echo '=== BEFORE — duplicate row breakdown by chain ==='
SELECT chain, COUNT(*) AS n
  FROM transactions
 WHERE chain LIKE 'eip155:%'
    OR chain LIKE 'solana:%'
 GROUP BY chain
 ORDER BY chain;

\echo ''
\echo '=== BEFORE — revenue (5월) by chain, includes duplicates ==='
SELECT chain,
       COUNT(*) AS n_rows,
       ROUND(SUM(amount)::numeric, 4) AS sum_usd
  FROM transactions
 WHERE time >= '2026-05-01'
   AND time <  '2026-06-01'
 GROUP BY chain
 ORDER BY chain;

-- ── safety guard ─────────────────────────────────────────────────────
-- Every CAIP-2 / solana:<addr> duplicate MUST have a matching
-- readable-chain counterpart. If not, the DELETE below would drop
-- unique attribution data — refuse to proceed.
\echo ''
\echo '=== safety guard — orphan duplicate count (must be 0) ==='
SELECT COUNT(*) AS orphan_duplicate_rows
  FROM transactions dup
 WHERE (dup.chain LIKE 'eip155:%' OR dup.chain LIKE 'solana:%')
   AND NOT EXISTS (
       SELECT 1 FROM transactions base
        WHERE base.tx_hash = dup.tx_hash
          AND base.chain IN ('base', 'arbitrum', 'polygon', 'solana')
   );

DO $$
DECLARE
    orphans INT;
BEGIN
    SELECT COUNT(*) INTO orphans
      FROM transactions dup
     WHERE (dup.chain LIKE 'eip155:%' OR dup.chain LIKE 'solana:%')
       AND NOT EXISTS (
           SELECT 1 FROM transactions base
            WHERE base.tx_hash = dup.tx_hash
              AND base.chain IN ('base', 'arbitrum', 'polygon', 'solana')
       );
    IF orphans > 0 THEN
        RAISE EXCEPTION
          'STOP: % orphan CAIP-2/solana:<addr> duplicate rows have no '
          'readable-chain counterpart. DELETE would lose attribution. '
          'Investigate before re-running.', orphans;
    END IF;
END$$;

-- ── Step A — promote dup attribution → base ──────────────────────────
-- Each readable-chain row gets the matching dup row's service_id,
-- attribution_source, feed_merchant_id, and is_x402_payment=TRUE. If
-- multiple dup rows share a tx_hash (shouldn't happen, but defensive),
-- pick the most recent by time.
\echo ''
\echo '=== Step A — promoting attribution from dup → base ==='

WITH dup_attr AS (
    SELECT DISTINCT ON (tx_hash)
           tx_hash,
           service_id,
           attribution_source,
           feed_merchant_id
      FROM transactions
     WHERE chain LIKE 'eip155:%' OR chain LIKE 'solana:%'
     ORDER BY tx_hash, time DESC NULLS LAST
)
UPDATE transactions base
   SET service_id        = dup_attr.service_id,
       attribution_source = dup_attr.attribution_source,
       feed_merchant_id  = dup_attr.feed_merchant_id,
       is_x402_payment   = TRUE
  FROM dup_attr
 WHERE base.tx_hash = dup_attr.tx_hash
   AND base.chain IN ('base', 'arbitrum', 'polygon', 'solana')
   -- Don't overwrite a readable-chain row that already has the same
   -- attribution_source (re-runs / partial prior cleanups stay idempotent).
   AND (
       base.attribution_source IS DISTINCT FROM dup_attr.attribution_source
       OR base.feed_merchant_id IS DISTINCT FROM dup_attr.feed_merchant_id
       OR base.service_id IS DISTINCT FROM dup_attr.service_id
       OR base.is_x402_payment IS DISTINCT FROM TRUE
   );

-- ── Step B — delete CAIP-2 / solana:<addr> duplicate rows ────────────
\echo ''
\echo '=== Step B — deleting CAIP-2 / solana:<addr> duplicate rows ==='

DELETE FROM transactions
 WHERE chain LIKE 'eip155:%' OR chain LIKE 'solana:%';

-- ── verification ─────────────────────────────────────────────────────
\echo ''
\echo '=== AFTER — chain breakdown (should be base/solana/arbitrum/polygon only) ==='
SELECT chain, COUNT(*) AS n
  FROM transactions
 GROUP BY chain
 ORDER BY chain;

\echo ''
\echo '=== AFTER — remaining CAIP-2 / solana:<addr> rows (must be 0) ==='
SELECT COUNT(*) AS remaining
  FROM transactions
 WHERE chain LIKE 'eip155:%' OR chain LIKE 'solana:%';

\echo ''
\echo '=== AFTER — revenue (5월) by chain ==='
SELECT chain,
       COUNT(*) AS n_rows,
       ROUND(SUM(amount)::numeric, 4) AS sum_usd
  FROM transactions
 WHERE time >= '2026-05-01'
   AND time <  '2026-06-01'
 GROUP BY chain
 ORDER BY chain;

\echo ''
\echo '=== AFTER — revenue (5월) total (compare against MetaMask balance) ==='
SELECT COUNT(*) AS n_rows,
       ROUND(SUM(amount)::numeric, 4) AS total_sum_usd
  FROM transactions
 WHERE time >= '2026-05-01'
   AND time <  '2026-06-01';

-- Change to ROLLBACK to dry-run.
COMMIT;
