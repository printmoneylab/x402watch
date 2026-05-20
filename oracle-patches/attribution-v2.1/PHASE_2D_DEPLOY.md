# Phase 2d — KR Crypto attribution backfill

Re-attributes KR Crypto's historical `transactions` from the
collapsed `service_id=14391` state to the correct per-endpoint
attribution. Builds on Phase 2c (merchant feed live, hourly timer
running).

**Approach.** The historical re-attribution reuses the exact code path
Phase 2c proved correct — `merchant_feed.py` in backfill mode
(`--since`), which walks the entire KR Crypto feed history via
`next_cursor`. No separate staging table, no jq. The SQL file only
does the safety backup, provenance marking, and verification.

**Prerequisite.** Pull the latest `merchant_feed.py` — it now has the
backfill mode (`--since` + cursor pagination):

```bash
cd /home/ubuntu/x402watch
git fetch origin && git pull --ff-only origin main
cp oracle-patches/attribution-v2.1/merchant_feed_indexer.py indexer/merchant_feed.py
venv/bin/python -c "import ast; ast.parse(open('indexer/merchant_feed.py').read()); print('OK')"
```

---

## Step 0 — pre-flight

```bash
# Phase 2c must already be live
sudo systemctl is-active x402watch-merchant-feed.timer    # expect: active
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c \
  "SELECT merchant_id, last_feed_seq FROM merchant_feed_state;"
# expect: kr-crypto row exists

# Regression baseline — must stay green through the whole backfill
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep x-x402-rewriter
# expect: v2.3
```

Pick a low-traffic window (KST night). The backfill itself is a few
seconds of DB work; the caution is just to keep `derive_global`'s
re-aggregation off peak.

---

## Step A — backup + pre-mark (SQL sections 1-3)

```bash
sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch \
  -v ON_ERROR_STOP=1 \
  < oracle-patches/attribution-v2.1/backfill_kr_crypto.sql
```

Running the whole file is safe — sections 5-6 are also in it, but they
are harmless before the backfill (section 5 finds nothing to mark yet,
section 6 just prints the pre-state). To run strictly section by
section, copy sections 1-3 out first. Either way, **confirm the
`BEFORE backfill` printout shows the collapse**: one fat row on
`service_id 14391` (~2,451 tx).

Verify the backup landed:

```bash
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c \
  "SELECT COUNT(*) FROM transactions_pre_v21_backup;"
# expect: equal to SELECT COUNT(*) FROM transactions
```

---

## Step B — merchant_feed.py backfill (dry-run, then real)

KR Crypto launched 2026-04-27. Walk the full history:

```bash
cd /home/ubuntu/x402watch

# B1. DRY-RUN — verify counts, writes nothing
venv/bin/python -m indexer.merchant_feed \
  --merchant kr-crypto \
  --feed-url https://api.printmoneylab.com \
  --since 2026-04-27T00:00:00Z --limit 5000 --dry-run
```

Expected dry-run JSON:
```json
{
  "merchant_id": "kr-crypto",
  "pages": <N>,
  "counts": {
    "accepted": ~1342,
    "rejected_seller": 0,
    "rejected_resource": <0, or the kr-news count if step 6b of
                          PHASE_2C_DEPLOY has not been done>,
    "rejected_amount": 0,
    "unchanged": 0
  }
}
```

- `accepted ≈ 1342` → matches KR Crypto's stats.jsonl payment_settled
  count. Good.
- `rejected_resource > 0` → almost certainly the kr-news endpoints
  still missing from `services`. Do PHASE_2C_DEPLOY step 6b (insert
  the 4 kr-news rows) first, then re-run the dry-run. `rejected_seller`
  must be 0.

```bash
# B2. REAL RUN — only after the dry-run looks right
venv/bin/python -m indexer.merchant_feed \
  --merchant kr-crypto \
  --feed-url https://api.printmoneylab.com \
  --since 2026-04-27T00:00:00Z --limit 5000
```

Idempotent: re-running is safe (SELECT-then-UPDATE/INSERT). It also
harmlessly overlaps the hourly timer's 24h window.

---

## Step C — post-mark + verify (SQL sections 5-6)

```bash
sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch \
  -v ON_ERROR_STOP=1 << 'SQL'
BEGIN;
UPDATE transactions
    SET attribution_source = 'legacy_unmatched', is_x402_payment = FALSE
WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
  AND attribution_source = 'legacy_collapse';
COMMIT;

SELECT attribution_source, COUNT(*) AS n, SUM(amount) AS usdc
  FROM transactions
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
 GROUP BY attribution_source ORDER BY n DESC;

SELECT service_id, COUNT(*) AS n, SUM(amount) AS usdc
  FROM transactions
 WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
   AND is_x402_payment = TRUE
 GROUP BY service_id ORDER BY n DESC;
SQL
```

Expected:
- `merchant_feed:kr-crypto` ≈ 1342, `legacy_unmatched` ≈ 1109.
- `service_id` distribution spread across all KR Crypto endpoints;
  `14391` far smaller than the pre-backfill ~2,451.

---

## Step D — re-aggregate

```bash
cd /home/ubuntu/x402watch
venv/bin/python -m indexer.derive_global
```

Then check the dashboard: each KR Crypto endpoint at
`https://x402.printmoneylab.com/services/<id>` should show its real
tx_total / volume instead of 0.

---

## Step E — regression checks

```bash
# PR #36 v2.3
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep x-x402-rewriter
# expect: v2.3
curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" | grep -iE "^(access-control|x-x402)"

# Step 6 dispute system
curl -s "https://x402.printmoneylab.com/api/disputes/buyer/0x15c3cdaeb8a0f00bb3a05f2bbbd86f0eebcd49c0"

# evm indexer still running (Phase 2b rollback intact)
sudo systemctl is-active x402watch-evm-indexer

# hourly merchant feed timer still fine
sudo systemctl is-active x402watch-merchant-feed.timer
```

---

## Reporting checklist (Moa fills with real numbers)

1. `transactions_pre_v21_backup` row count == `transactions` row count.
2. BEFORE: `service_id` distribution for KR Crypto seller (the collapse).
3. Backfill dry-run `counts` JSON.
4. Backfill real-run `counts` JSON (`pages`, `accepted`).
5. AFTER: `attribution_source` distribution
   (`merchant_feed:kr-crypto` vs `legacy_unmatched`).
6. AFTER: `service_id` distribution (the spread).
7. Solana INSERT count (`feed_merchant_id='kr-crypto' AND chain LIKE 'solana:%'`).
8. `derive_global` summary output.
9. Regression checks (step E) all green.

---

## Rollback

Full restore — see `backfill_kr_crypto.sql` final section. The backup
table `transactions_pre_v21_backup` is the single source of truth for
undo; it is never modified by any step here.
