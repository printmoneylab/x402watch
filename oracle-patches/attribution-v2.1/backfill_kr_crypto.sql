-- Phase 2d — KR Crypto attribution backfill
--
-- Permanent location on Oracle:
--   /home/ubuntu/x402watch/migrations/v21_attribution_backfill.sql
--
-- REVISED for Phase 2c findings. The original draft loaded stats.jsonl
-- into a staging table via jq and did the attribution join in SQL.
-- That is replaced: the historical re-attribution is now done by
-- running `indexer/merchant_feed.py` in BACKFILL MODE (--since), which
-- reuses the exact, already-live-verified code path
--   KR Crypto x402watch_feed.py  →  x402watch merchant_feed.py
-- — so stats.jsonl parsing, timestamp/`type`-field handling, resource
-- URL normalisation, Ed25519 verification, and the
-- SELECT-then-UPDATE/INSERT attribution are all the SAME code that
-- Phase 2c proved correct (dry-run accepted 51, rejected 0).
--
-- This SQL file therefore only does the parts merchant_feed.py does
-- NOT: the safety backup, the pre/post provenance marking, and the
-- verification queries. The actual data move happens in step B below.
--
-- ─────────────────────────────────────────────────────────────────
-- RUN ORDER
--   A. This file, sections 1-3  (schema + backup + pre-mark)
--   B. merchant_feed.py backfill (shell — see section 4 comment)
--   C. This file, sections 5-7  (post-mark + verify)
--   D. derive_global             (shell — see section 7 comment)
-- ─────────────────────────────────────────────────────────────────


-- ===================================================================
-- A.  Sections 1-3 — run before the merchant_feed.py backfill
-- ===================================================================
BEGIN;

-- ─── 1. Schema additions (idempotent) ───────────────────────────────
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS attribution_source TEXT,
    ADD COLUMN IF NOT EXISTS feed_merchant_id   TEXT,
    ADD COLUMN IF NOT EXISTS is_x402_payment    BOOLEAN;

CREATE INDEX IF NOT EXISTS transactions_attribution_idx
    ON transactions (attribution_source, time DESC);

-- Non-unique lookup index on (tx_hash, chain). transactions is a
-- TimescaleDB hypertable partitioned on `time`; a UNIQUE index that
-- omits the partition column is rejected — so the merchant feed
-- indexer + this backfill dedupe with explicit SELECT-then-UPDATE/
-- INSERT, and this index keeps that lookup fast.
CREATE INDEX IF NOT EXISTS transactions_txhash_chain_idx
    ON transactions (tx_hash, chain);

CREATE TABLE IF NOT EXISTS merchant_feed_keys (
    merchant_id       TEXT NOT NULL,
    key_id            TEXT NOT NULL,
    public_key_b64url TEXT NOT NULL,
    feed_base_url     TEXT,
    valid_from        TIMESTAMPTZ NOT NULL,
    valid_until       TIMESTAMPTZ NOT NULL,
    registered_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at        TIMESTAMPTZ,
    PRIMARY KEY (merchant_id, key_id)
);

CREATE TABLE IF NOT EXISTS merchant_feed_state (
    merchant_id    TEXT PRIMARY KEY,
    last_feed_seq  BIGINT NOT NULL,
    last_fetch_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── 2. Backup table — full snapshot, NEVER modified ────────────────
-- `CREATE TABLE IF NOT EXISTS … AS SELECT` is atomic + idempotent: a
-- re-run sees the table exists and skips the SELECT, so the backup is
-- never doubled. Preserved indefinitely until manually dropped.
CREATE TABLE IF NOT EXISTS transactions_pre_v21_backup AS
SELECT * FROM transactions;

-- ─── 3. Pre-mark every existing row as legacy_collapse ──────────────
-- Establishes a known starting provenance. The merchant_feed.py
-- backfill (step B) then OVERWRITES attribution_source to
-- 'merchant_feed:kr-crypto' for every real x402 settlement it
-- recognises. Whatever stays 'legacy_collapse' afterwards on the KR
-- Crypto seller wallet is, by elimination, a non-x402 USDC transfer
-- (CEX deposit, manual send, …) and is handled in section 5.
UPDATE transactions
    SET attribution_source = 'legacy_collapse'
WHERE attribution_source IS NULL;

COMMIT;

-- Sanity snapshot before the data move:
SELECT 'BEFORE backfill — KR Crypto seller distribution' AS section;
SELECT service_id, COUNT(*) AS n, SUM(amount) AS usdc
  FROM transactions
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
 GROUP BY service_id
 ORDER BY n DESC;
-- Expected: a single fat row on service_id 14391 (~2,451 tx) — the
-- collapse bug. After backfill this spreads across all KR endpoints.


-- ===================================================================
-- B.  merchant_feed.py BACKFILL — run in a shell, NOT in psql
-- ===================================================================
-- KR Crypto launched 2026-04-27. Walk the entire feed history with a
-- big page size; merchant_feed.py follows next_cursor to the end.
--
--   cd /home/ubuntu/x402watch
--   # dry-run first — verify counts, write nothing
--   venv/bin/python -m indexer.merchant_feed \
--     --merchant kr-crypto \
--     --feed-url https://api.printmoneylab.com \
--     --since 2026-04-27T00:00:00Z --limit 5000 --dry-run
--
--   # then for real
--   venv/bin/python -m indexer.merchant_feed \
--     --merchant kr-crypto \
--     --feed-url https://api.printmoneylab.com \
--     --since 2026-04-27T00:00:00Z --limit 5000
--
-- Expected output: {"pages": N, "counts": {"accepted": ~1342,
--   "rejected_resource": <kr-news count until step 6b of PHASE_2C
--   is done>, ...}}. Every accepted row is UPDATEd in place (matched
--   tx_hash) or INSERTed (KR Crypto Solana settlements x402watch
--   never indexed), with attribution_source='merchant_feed:kr-crypto'.


-- ===================================================================
-- C.  Sections 5-6 — run AFTER the merchant_feed.py backfill
-- ===================================================================
BEGIN;

-- ─── 5. Mark the non-x402 remainder as legacy_unmatched ─────────────
-- Any KR Crypto seller row still tagged 'legacy_collapse' was not in
-- the merchant feed → not an x402 payment. Mark it so it is excluded
-- from x402 traffic stats without being deleted.
UPDATE transactions
    SET attribution_source = 'legacy_unmatched',
        is_x402_payment    = FALSE
WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
  AND attribution_source = 'legacy_collapse';

-- ─── 6. Verification (read-only) ────────────────────────────────────
SELECT 'AFTER backfill — attribution_source distribution (KR Crypto)' AS section;
SELECT attribution_source, COUNT(*) AS n, SUM(amount) AS usdc
  FROM transactions
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
 GROUP BY attribution_source
 ORDER BY n DESC;
-- Expected:
--   merchant_feed:kr-crypto   ≈ 1342  (the real x402 settlements)
--   legacy_unmatched          ≈ 1109  (non-x402 USDC transfers)

SELECT 'AFTER backfill — service_id distribution (x402 payments only)' AS section;
SELECT service_id, COUNT(*) AS n, SUM(amount) AS usdc
  FROM transactions
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
   AND is_x402_payment = TRUE
 GROUP BY service_id
 ORDER BY n DESC;
-- Expected: spread across all KR Crypto endpoints — kr-prices the
-- majority, kr-sentiment / arbitrage-scanner / kimchi-premium etc.
-- now non-zero. service_id 14391 should be much smaller than the
-- pre-backfill ~2,451.

SELECT 'AFTER backfill — Solana settlements that got INSERTed fresh' AS section;
SELECT COUNT(*) AS solana_inserted
  FROM transactions
 WHERE feed_merchant_id = 'kr-crypto'
   AND chain LIKE 'solana:%';
-- Expected: ~61 (KR Crypto's Solana payments — indexer/solana.py never
-- captured these; the merchant feed INSERTed them).

COMMIT;


-- ===================================================================
-- D.  derive_global — run in a shell, NOT in psql
-- ===================================================================
--   cd /home/ubuntu/x402watch
--   venv/bin/python -m indexer.derive_global
--
-- Re-aggregates services.tx_total / volume / real_volume_pct /
-- wash_pct and buyer_seller_labels from the corrected transactions.
-- After this the dashboard shows each KR Crypto endpoint's true
-- numbers.


-- ===================================================================
-- ROLLBACK
-- ===================================================================
-- Full restore from the section-2 backup:
--
--   BEGIN;
--   TRUNCATE transactions;
--   INSERT INTO transactions SELECT * FROM transactions_pre_v21_backup;
--   COMMIT;
--
-- (The added columns can stay — they're harmless. Drop them too if a
--  total revert is wanted:
--   ALTER TABLE transactions
--     DROP COLUMN attribution_source,
--     DROP COLUMN feed_merchant_id,
--     DROP COLUMN is_x402_payment; )
--
-- Partial rollback — undo only the merchant-feed re-attribution,
-- keep the schema:
--   UPDATE transactions t
--      SET service_id        = b.service_id,
--          attribution_source= b.attribution_source,
--          feed_merchant_id  = b.feed_merchant_id,
--          is_x402_payment   = b.is_x402_payment
--   FROM transactions_pre_v21_backup b
--   WHERE t.tx_hash = b.tx_hash AND t.chain = b.chain;
--   DELETE FROM transactions
--    WHERE feed_merchant_id = 'kr-crypto'
--      AND tx_hash NOT IN (SELECT tx_hash FROM transactions_pre_v21_backup);
