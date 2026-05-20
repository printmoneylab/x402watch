# Phase 2c — Merchant Feed deploy (KR Crypto first)

Stands on its own — does NOT depend on Phase 2b (the evm.py patch is
on hold pending the P4 fix for `index_chain`). Merchant feed writes
attribution directly to `transactions.service_id` via tx_hash, so it
corrects KR Crypto's data regardless of what `evm.py` does going
forward.

## 0. Pre-flight

```bash
# Confirm Phase 2b is rolled back and the indexer is healthy.
ssh ubuntu@168.138.195.65 "tail -3 /home/ubuntu/x402watch/indexer/evm.py"
# expect: original load_seller_map / no v2.1 markers
sudo systemctl status x402watch-evm-indexer --no-pager | head -5
# expect: active (running)

# Confirm the cryptography lib is on both boxes.
ssh ubuntu@168.138.195.65 "/home/ubuntu/x402watch/venv/bin/python -c 'import cryptography; print(cryptography.__version__)'"
ssh ubuntu@168.138.195.65 "/home/ubuntu/KRCryptoAPI/venv/bin/python -c 'import cryptography; print(cryptography.__version__)'"
# install if missing: venv/bin/pip install cryptography
```

## 1. Pull the patch onto both boxes

```bash
ssh ubuntu@168.138.195.65
cd /home/ubuntu/x402watch && git fetch origin && git pull --ff-only origin main
ls oracle-patches/attribution-v2.1/
```

## 2. Schema — apply on x402watch Postgres

The merchant feed needs `merchant_feed_keys`, `merchant_feed_state`,
the `transactions.attribution_source/feed_merchant_id/is_x402_payment`
columns, and the `(tx_hash, chain)` lookup index. All of these are in
`backfill_kr_crypto.sql` §1. Apply just §1 first (it is idempotent and
safe to run before the backfill itself):

```bash
sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch << 'SQL'
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS attribution_source TEXT,
    ADD COLUMN IF NOT EXISTS feed_merchant_id   TEXT,
    ADD COLUMN IF NOT EXISTS is_x402_payment    BOOLEAN;
CREATE INDEX IF NOT EXISTS transactions_attribution_idx
    ON transactions (attribution_source, time DESC);
CREATE INDEX IF NOT EXISTS transactions_txhash_chain_idx
    ON transactions (tx_hash, chain);
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
SQL
```

Note: `transactions_txhash_chain_idx` is a **non-unique** index. We
cannot make it UNIQUE because `transactions` is a TimescaleDB
hypertable partitioned on `time` and a unique index must include the
partition column. The indexer + backfill therefore dedupe with
explicit SELECT-then-UPDATE/INSERT rather than `ON CONFLICT`.

## 3. KR Crypto side — generate the Ed25519 key + install the endpoint

On the KR Crypto box:

```bash
ssh ubuntu@168.138.195.65
mkdir -p /home/ubuntu/KRCryptoAPI/secrets

# Generate the signing key (one-off).
/home/ubuntu/KRCryptoAPI/venv/bin/python << 'PY'
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import base64
k = Ed25519PrivateKey.generate()
pem = k.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
open("/home/ubuntu/KRCryptoAPI/secrets/x402watch_feed.ed25519.pem", "wb").write(pem)
pub = k.public_key().public_bytes(
    encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
print("PUBLIC_KEY_B64URL:", base64.urlsafe_b64encode(pub).rstrip(b"=").decode())
PY
chmod 600 /home/ubuntu/KRCryptoAPI/secrets/x402watch_feed.ed25519.pem
```

Copy the printed `PUBLIC_KEY_B64URL` — needed in step 5.

Install the feed endpoint:

```bash
cp /home/ubuntu/x402watch/oracle-patches/attribution-v2.1/merchant_feed_kr_crypto.py \
   /home/ubuntu/KRCryptoAPI/app/x402watch_feed.py
```

Add to KR Crypto's `.env`:

```
KR_FEED_PRIVATE_KEY_PATH=/home/ubuntu/KRCryptoAPI/secrets/x402watch_feed.ed25519.pem
KR_FEED_PUBLIC_KEY_ID=kr-crypto-feed-2026-05-20
KR_FEED_MERCHANT_ID=kr-crypto
KR_STATS_PATH=/home/ubuntu/KRCryptoAPI/stats.jsonl
KR_FEED_SEQ_PATH=/home/ubuntu/KRCryptoAPI/var/x402watch_feed_seq
```

Mount the router in KR Crypto's FastAPI app (the file that builds the
`FastAPI()` instance):

```python
from app.x402watch_feed import router as x402watch_feed_router
app.include_router(x402watch_feed_router)
```

Restart KR Crypto's API service, then smoke-test the feed:

```bash
sudo systemctl restart <kr-crypto-api-service>
curl -s "https://api.printmoneylab.com/.well-known/x402watch-feed.json?limit=5" \
  | python3 -m json.tool | head -40
# expect: feed_version=1, merchant_id=kr-crypto, settlements[], signature{}
```

## 4. Verify the feed signature locally (before registering)

```bash
/home/ubuntu/x402watch/venv/bin/python << 'PY'
import base64, json, urllib.request
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

PUB_B64URL = "<paste PUBLIC_KEY_B64URL from step 3>"

with urllib.request.urlopen(
        "https://api.printmoneylab.com/.well-known/x402watch-feed.json?limit=50") as r:
    body = json.load(r)

sig = body.pop("signature")
msg = json.dumps(body, sort_keys=True, separators=(",", ":"),
                 ensure_ascii=False).encode()
pad = "=" * ((4 - len(PUB_B64URL) % 4) % 4)
pub = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(PUB_B64URL + pad))
sv = sig["value"]; sv += "=" * ((4 - len(sv) % 4) % 4)
try:
    pub.verify(base64.urlsafe_b64decode(sv), msg)
    print("SIGNATURE OK — feed is authentic")
    print("settlements in this page:", len(body.get("settlements", [])))
except InvalidSignature:
    print("SIGNATURE FAIL — canonicalisation mismatch, do not register")
PY
```

If this prints `SIGNATURE OK` the protocol round-trips correctly. If it
prints `SIGNATURE FAIL`, the canonical-JSON encodings on the two sides
diverged — stop and reconcile before going further.

## 5. Register KR Crypto's key on x402watch

```bash
sudo docker exec -i x402watch-postgres psql -U x402watch -d x402watch << 'SQL'
INSERT INTO merchant_feed_keys
    (merchant_id, key_id, public_key_b64url, feed_base_url, valid_from, valid_until)
VALUES
    ('kr-crypto', 'kr-crypto-feed-2026-05-20',
     '<PASTE PUBLIC_KEY_B64URL>',
     'https://api.printmoneylab.com',
     '2026-05-20T00:00:00Z', '2027-05-20T00:00:00Z')
ON CONFLICT (merchant_id, key_id) DO UPDATE
  SET public_key_b64url = EXCLUDED.public_key_b64url,
      feed_base_url = EXCLUDED.feed_base_url,
      valid_until = EXCLUDED.valid_until;
SQL
```

## 6. Install the indexer-side fetcher

```bash
cp /home/ubuntu/x402watch/oracle-patches/attribution-v2.1/merchant_feed_indexer.py \
   /home/ubuntu/x402watch/indexer/merchant_feed.py
```

Dry-run against KR Crypto (no DB writes):

```bash
cd /home/ubuntu/x402watch
venv/bin/python -m indexer.merchant_feed --merchant kr-crypto \
  --feed-url https://api.printmoneylab.com --dry-run
# expect JSON: {"merchant_id":"kr-crypto","counts":{"accepted":N,...}}
```

If the dry-run shows `accepted > 0` and no `rejected_*` surprises,
run for real:

```bash
venv/bin/python -m indexer.merchant_feed --merchant kr-crypto \
  --feed-url https://api.printmoneylab.com
```

## 7. Schedule hourly polling

Add to the existing indexer cron / timer, or a dedicated timer:

```ini
# /etc/systemd/system/x402watch-merchant-feed.service
[Unit]
Description=x402watch merchant feed poller
[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/x402watch
EnvironmentFile=/home/ubuntu/x402watch/.env
ExecStart=/home/ubuntu/x402watch/venv/bin/python -m indexer.merchant_feed

# /etc/systemd/system/x402watch-merchant-feed.timer
[Unit]
Description=Poll merchant feeds hourly
[Timer]
OnCalendar=hourly
Persistent=true
[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now x402watch-merchant-feed.timer
```

## 8. Verify attribution corrected

```bash
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
SELECT service_id, COUNT(*) AS n, SUM(amount) AS usdc
FROM transactions
WHERE attribution_source = 'merchant_feed:kr-crypto'
GROUP BY service_id ORDER BY n DESC;
"
# expect: KR Crypto's 11 endpoints each with their real counts —
#   kr-prices the majority, kr-sentiment / arbitrage-scanner etc.
#   now non-zero.
```

Then re-aggregate service stats + buyer labels:

```bash
cd /home/ubuntu/x402watch
venv/bin/python -m indexer.derive_global
```

## 9. Regression checks (must stay green)

```bash
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep x-x402-rewriter
# expect: v2.3
curl -s "https://x402.printmoneylab.com/api/disputes/buyer/0x15c3cdaeb8a0f00bb3a05f2bbbd86f0eebcd49c0"
# expect: 200 JSON
sudo systemctl status x402watch-evm-indexer --no-pager | head -3
# expect: active (running) — Phase 2b rollback still in place
```

## 10. Rollback

```bash
# Stop the poller
sudo systemctl disable --now x402watch-merchant-feed.timer

# Undo merchant-feed attribution (restore from the v2.1 backup, only
# the rows the feed touched)
sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c "
UPDATE transactions t
   SET service_id = b.service_id,
       attribution_source = b.attribution_source,
       feed_merchant_id = b.feed_merchant_id,
       is_x402_payment = b.is_x402_payment
FROM transactions_pre_v21_backup b
WHERE t.tx_hash = b.tx_hash AND t.chain = b.chain
  AND t.attribution_source = 'merchant_feed:kr-crypto';
"
# Rows the feed INSERTed fresh (KR Crypto Solana) won't be in the
# backup; delete them explicitly if a full revert is wanted:
#   DELETE FROM transactions
#   WHERE attribution_source = 'merchant_feed:kr-crypto'
#     AND tx_hash NOT IN (SELECT tx_hash FROM transactions_pre_v21_backup);
```

Note: the §2 backup table `transactions_pre_v21_backup` is created by
the Phase 2d backfill SQL. If you run Phase 2c standalone before the
backfill, take a backup first:
`CREATE TABLE IF NOT EXISTS transactions_pre_v21_backup AS SELECT * FROM transactions;`

## Order of operations summary

```
2c-step 2  schema (idempotent, safe anytime)
2c-step 3  KR Crypto key + endpoint
2c-step 4  local signature self-verify   ← gate: must say SIGNATURE OK
2c-step 5  register key on x402watch
2c-step 6  indexer dry-run               ← gate: accepted > 0
2c-step 6  indexer real run
2c-step 7  hourly timer
2c-step 8  derive_global re-aggregate
2c-step 9  regression checks
```
