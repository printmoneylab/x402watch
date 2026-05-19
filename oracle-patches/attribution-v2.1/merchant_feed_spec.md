# x402watch Merchant Feed Protocol v1.0

Opt-in mechanism for x402 merchants to publish their own payment ledger
to x402watch with cryptographic authenticity. Solves the on-chain
attribution gap: x402 settlement transactions don't carry `resource_url`,
so external observers cannot map `(tx_hash → endpoint)` for merchants
that operate multiple endpoints under one seller wallet. Each merchant
runs a small public endpoint that lists their own settled payments,
signed with an Ed25519 key registered with x402watch.

## 1. Endpoint shape

```
GET https://<merchant-domain>/.well-known/x402watch-feed.json
GET https://<merchant-domain>/api/v1/x402watch-feed.json
```

Either path acceptable. `.well-known/` preferred for discoverability;
`/api/v1/` acceptable for merchants whose ops infra already lives under
`/api`. x402watch indexer probes `.well-known/` first, falls back to
`/api/v1/`.

Query parameters:

| param | type | default | meaning |
|---|---|---|---|
| `since` | ISO 8601 | (24h ago) | Lower bound for `settled_at`. Merchant SHOULD honor and return only rows ≥ since |
| `limit` | int | 500 | Page size. Max 5000. Merchant MUST cap silently |
| `cursor` | string | (none) | Opaque pagination cursor returned on a previous response |

## 2. Response shape

```json
{
  "feed_version": 1,
  "merchant_id": "kr-crypto",
  "seller_addresses": [
    "0xcF9223eCe895258dEa8D288AEBcf846Ab8E342fB",
    "3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9"
  ],
  "feed_seq": 142857,
  "issued_at": "2026-05-19T12:34:56Z",
  "window": {
    "since": "2026-05-18T12:34:56Z",
    "until": "2026-05-19T12:34:56Z"
  },
  "settlements": [
    {
      "tx_hash": "0xabc...123",
      "chain": "eip155:8453",
      "settled_at": "2026-05-19T11:22:33Z",
      "resource_url": "https://api.printmoneylab.com/api/v1/kr-prices",
      "payer": "0x15c3cdaeb8a0f00bb3a05f2bbbd86f0eebcd49c0",
      "seller": "0xcF9223eCe895258dEa8D288AEBcf846Ab8E342fB",
      "amount_usdc": "1000",
      "price_usd": 0.001,
      "x402_version": 2
    },
    {
      "tx_hash": "5o...solSignature...",
      "chain": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
      "settled_at": "2026-05-19T10:11:22Z",
      "resource_url": "https://api.printmoneylab.com/api/v1/kr-sentiment",
      "payer": "AFTAzyW25oQaeAo3k1he8r4EyeBLABdZQrkm5x3SLkWi",
      "seller": "3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9",
      "amount_usdc": "50000",
      "price_usd": 0.05,
      "x402_version": 2
    }
  ],
  "next_cursor": "eyJzZXEiOiAxNDI4NTd9",
  "signature": {
    "alg": "Ed25519",
    "key_id": "kr-crypto-feed-2026-05-19",
    "value": "base64url(sig over canonical JSON of all preceding fields)"
  }
}
```

### Field semantics

- `feed_version` (int): protocol version. Currently `1`. Indexer rejects
  feeds with unknown version.
- `merchant_id` (string): stable identifier the merchant registered with
  x402watch out of band. NOT the same as the seller wallet — a merchant
  can rotate wallets without rotating identity.
- `seller_addresses` (array): every seller wallet this merchant claims.
  The indexer cross-references against `services.seller_address` to map
  feed entries to existing services rows.
- `feed_seq` (int): monotonically increasing per merchant. The indexer
  refuses any feed whose `feed_seq` is less than or equal to the highest
  it has previously accepted for that `merchant_id`. This prevents
  replay attacks where an attacker re-publishes an old (already-honest)
  feed snapshot to flush newer corrections.
- `issued_at` (RFC 3339): server time of feed generation. Indexer
  rejects feeds where `issued_at` is more than 24h in the past or
  more than 5 min in the future (clock skew tolerance).
- `window` (object): merchant promises the feed contains every settled
  payment in `[since, until)`. Indexer uses this to detect gaps.
- `settlements` (array): the payment rows. Each row's `tx_hash` is the
  primary join key against `transactions` on x402watch side.
- `next_cursor`: present iff more pages exist for this query. Pass back
  to merchant on the next request.
- `signature`: Ed25519 over the canonical JSON of every preceding field
  (signature itself excluded). Canonical JSON = JCS (RFC 8785).

### Settlement row constraints

- `tx_hash`: case-preserved for Solana base58; lowercased for EVM 0x...
- `chain`: CAIP-2 format (`eip155:8453`, `solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp`)
- `resource_url`: MUST be a URL the merchant actually serves. Indexer
  may probe the URL out of band to confirm it returns 402 with the
  expected payTo.
- `payer`: chain-appropriate format (hex for EVM, base58 for Solana)
- `amount_usdc`: integer string, base unit (6 decimals for USDC on Base,
  6 on Solana). MUST match the on-chain transferred amount.
- `price_usd`: floating-point dollar price. Indexer cross-checks against
  `services.price_amount` for the resource_url and flags mismatch as
  warning but does not reject.

## 3. Key registration

Out-of-band: merchant emails / commits to GitHub:
```
merchant_id: kr-crypto
ed25519_public_keys:
  - key_id: kr-crypto-feed-2026-05-19
    public_key_b64url: "AAAA..."          # 32 bytes raw, base64url-encoded
    valid_from: "2026-05-19T00:00Z"
    valid_until: "2027-05-19T00:00Z"
```

x402watch maintains a registry table:
```sql
CREATE TABLE merchant_feed_keys (
    merchant_id     TEXT NOT NULL,
    key_id          TEXT NOT NULL,
    public_key_b64url TEXT NOT NULL,
    valid_from      TIMESTAMPTZ NOT NULL,
    valid_until     TIMESTAMPTZ NOT NULL,
    registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ,
    PRIMARY KEY (merchant_id, key_id)
);
```

Key rotation: merchant publishes both old + new key for at least 7
days. Indexer accepts feeds signed by any valid (non-revoked) key.

## 4. Verification flow on x402watch side

For each fetched feed:

1. Fetch `https://merchant/.well-known/x402watch-feed.json?since=…`.
   Timeout 10 s. Max body size 16 MiB.
2. Reject if `feed_version != 1`.
3. Look up `merchant_id` in registry. Reject if unknown.
4. For each `signature.key_id`, look up the matching public key.
   Reject if no key found, or key is revoked, or `issued_at` falls
   outside `(valid_from, valid_until)`.
5. Canonicalize the body (JCS) excluding the `signature.value` field,
   verify the Ed25519 signature. Reject on failure.
6. Check `feed_seq > last_accepted_feed_seq[merchant_id]`. Reject on
   replay.
7. For each settlement:
   - Reject if `seller` not in `seller_addresses`.
   - Reject if `resource_url` not in `services.resource_url` for any
     row owned by `seller`.
   - Otherwise, accept: `INSERT INTO transactions ON CONFLICT (tx_hash,
     chain) DO UPDATE SET service_id = EXCLUDED.service_id,
     attribution_source = 'merchant_feed:' || merchant_id`.
8. Update `last_accepted_feed_seq[merchant_id] = feed_seq`.
9. Telemetry: emit a `merchant_feed_fetch` row to stats.jsonl with
   counts (accepted / rejected / reasons).

## 5. Indexer schedule

Default: every 60 minutes per merchant. On startup, indexer queries
each known merchant with `since = max(last_accepted.settled_at, NOW() - 24h)`.

Backoff: on feed fetch failure (5xx, signature failure, replay), retry
in 5/15/60 min with capped exponential backoff. After 3 consecutive
failures, send a Telegram alert and pause that merchant's fetch for
24h.

## 6. Schema changes on x402watch transactions table

```sql
ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS attribution_source TEXT,
    ADD COLUMN IF NOT EXISTS feed_merchant_id TEXT,
    ADD COLUMN IF NOT EXISTS is_x402_payment BOOLEAN;

CREATE INDEX IF NOT EXISTS transactions_attribution_idx
    ON transactions (attribution_source, time DESC);

-- Allowed attribution_source values:
--   'legacy_collapse'   : pre-v2.1 rows (MIN(id) bug)
--   'price_match'       : v2.1 evm.py patch matched (seller, amount)
--   'price_match_lossy' : v2.1 patch matched but same-price collision picked oldest
--   'merchant_feed:<merchant_id>'  : Ed25519-verified merchant feed
--   'unattributed'      : seller wallet matches but no service row at that amount
```

## 7. Anti-abuse properties

- **Replay protection**: monotonic `feed_seq` per merchant.
- **Forgery protection**: Ed25519 signature over canonical body.
- **Inflation protection**: each `settlement.tx_hash` is checked against
  the on-chain transaction (Base RPC / Solana RPC) by the indexer.
  Mismatch on amount / payTo / chain → row rejected, alert raised.
  Merchant cannot claim payments that didn't happen.
- **Cross-merchant attribution attempts**: indexer requires
  `seller IN seller_addresses` per row. Merchant cannot claim payments
  for someone else's wallet.

## 8. Privacy posture

The feed contains only data that is already public on-chain (tx_hash,
payer, amount, chain) plus the resource_url that x402watch already
displays in service detail pages. No additional PII exposed.

## 9. Reference implementations (this directory)

- `merchant_feed_kr_crypto.py` — KR Crypto-side Python endpoint that
  reads `/home/ubuntu/KRCryptoAPI/stats.jsonl` and emits a signed JSON
  feed. Drop-in for the existing FastAPI app at api.printmoneylab.com.
- `merchant_feed_indexer.py` — x402watch-side fetcher that polls
  registered merchants, verifies signatures, and writes to the
  `transactions` table with `attribution_source='merchant_feed:…'`.

## 10. Future extensions (not v1)

- WebSocket push instead of poll (low priority — hourly is fine).
- Settlement chain proof: each row could include a partial Merkle path
  proving the tx_hash belongs to a Base block. Currently we accept the
  merchant's claim subject to RPC verification on the indexer side.
- Multi-merchant aggregator endpoints (one feed covering N merchants).
