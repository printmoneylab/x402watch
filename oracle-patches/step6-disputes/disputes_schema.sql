-- Step 6 — label_disputes + recompute_queue tables.
--
-- Run once on the Oracle Postgres (timescaledb, docker port 5433):
--
--   psql -h 127.0.0.1 -p 5433 -U x402watch -d x402watch \
--        -f /home/ubuntu/x402watch/migrations/disputes_schema.sql
--
-- Idempotent: safe to re-run (CREATE TABLE / INDEX IF NOT EXISTS).
--
-- The CHECK on `reason` mirrors the frontend's 32..1000 bound; the
-- unique dedupe index makes "same reporter filed on this buyer today"
-- rejectable at the DB layer without an explicit ratelimit table.

BEGIN;

CREATE TABLE IF NOT EXISTS label_disputes (
    id                 SERIAL PRIMARY KEY,
    buyer_address      TEXT NOT NULL,
    seller_address     TEXT,
    reporter_address   TEXT,
    reporter_ip        TEXT,                      -- best-effort, set by the proxy
    reason             TEXT NOT NULL CHECK (char_length(reason) BETWEEN 32 AND 1000),
    current_label      TEXT NOT NULL,
    current_confidence NUMERIC(3,2),
    status             TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','reviewed','resolved','rejected')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at        TIMESTAMPTZ,
    resolution_note    TEXT
);

CREATE INDEX IF NOT EXISTS label_disputes_buyer_idx
    ON label_disputes (buyer_address, created_at DESC);
CREATE INDEX IF NOT EXISTS label_disputes_status_idx
    ON label_disputes (status, created_at DESC);
CREATE INDEX IF NOT EXISTS label_disputes_seller_idx
    ON label_disputes (seller_address, created_at DESC)
    WHERE seller_address IS NOT NULL;

-- 24h same-buyer-per-reporter dedupe — bucket by (buyer, reporter or
-- IP, calendar day). Postgres collapses the day truncation so a single
-- reporter only gets one row per buyer per day.
CREATE UNIQUE INDEX IF NOT EXISTS label_disputes_dedupe_idx
    ON label_disputes (
        buyer_address,
        COALESCE(reporter_address, ''),
        COALESCE(reporter_ip, ''),
        (date_trunc('day', created_at))
    );

CREATE TABLE IF NOT EXISTS recompute_queue (
    buyer_address TEXT PRIMARY KEY,
    triggered_by  INTEGER REFERENCES label_disputes(id) ON DELETE SET NULL,
    pending_count INTEGER NOT NULL DEFAULT 1,
    added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS recompute_queue_pending_idx
    ON recompute_queue (added_at)
    WHERE processed_at IS NULL;

COMMIT;

-- Verify after apply:
--   \d label_disputes
--   \d recompute_queue
--   SELECT COUNT(*) FROM label_disputes;  -- expect 0
--   SELECT COUNT(*) FROM recompute_queue; -- expect 0
