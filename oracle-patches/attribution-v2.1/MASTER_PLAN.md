# x402watch attribution v2.1 — master plan

## 0. Status board

| Item | Status | Notes |
|---|---|---|
| Root cause | ✅ confirmed | `evm.py:165` 의 `GROUP BY seller_address` + `MIN(id)` collapses N endpoints → 1 service_id |
| Option A — price-based fallback | 🟡 ON HOLD — needs P4 | `evm_attribution_patch.py` P1/P2/P3 applied cleanly but regressed: `index_chain` (~L264) does `[pad_topic_address(a) for a in seller_map.keys()]` — keys are now tuples → `AttributeError: 'tuple' object has no attribute 'lower'`. Rolled back. Resume after Phase 2c+2d with a P4 patch (see §8) |
| Option B — CDP settlement log | ❌ infeasible | Verified against `coinbase/cdp-sdk` `X402FacilitatorApi.java` + `coinbase/x402` Python facilitator: no settlement-log endpoint exists. `verify` / `settle` / `discovery/resources` only. 401s on `/discovery/settlements` were default-404-as-401 |
| Option C — calldata parsing | ❌ structural | x402 settles via `USDC.transferWithAuthorization` (EIP-3009) which has no resource-URL slot; resource_url lives only in the X-Payment HTTP header |
| Option D — merchant feed | ✅ designed (spec + KR/indexer stubs) | Opt-in. 100% accurate for adopting merchants. Ed25519-signed JSON feed at `merchant.example.com/api/v1/x402watch-feed.json` |
| Option E — facilitator proxy | 🔜 Phase 3 (deferred) | Would give 100% across all merchants but requires running our own x402 facilitator or transparent proxy |
| Backfill — KR Crypto via stats.jsonl | ✅ written (`backfill_kr_crypto.sql`) | idempotent, soft-delete via `attribution_source` column |
| Solana indexing fix | 🟡 separate work item | `indexer/solana.py` currently produces 9 rows total; KR Crypto's 61 Base/Solana payments would be canonical truth set |
| Noise removal (non-x402 USDC transfers) | 🟡 separate work item | x402watch indexed 2,451 vs KR Crypto's 1,342 actual settlements → ~1,109 non-payment transfers wrongly attributed |

## 1. Why we shipped v2.0 with a broken input layer

The v2.0 4-layer wash filter + 9-label taxonomy is algorithmically sound but
operated on attribution-collapsed inputs. KR Crypto's 11 endpoints all
collapsed to `service_id=14391`, so:

- `services.tx_total` for the 10 other KR Crypto rows = 0 (looks like dead endpoints)
- `services.tx_total` for #14391 = inflated (2,451 vs the real ~1,281 Base settlements + ~1,109 non-payment USDC transfers wrongly bucketed)
- `buyer_seller_labels` for KR Crypto buyers all got attributed to the (buyer, #14391) pair, so per-pair signals are diluted
- The KR Crypto kr-prices "96.4% → 0% wash" headline that anchored v2.0's launch is a partial truth: the algorithm correctly removed false positives, but it removed them from a service whose underlying data was the aggregation of 11 endpoints anyway

This means v2.1 has to do three things together:
1. Fix the attribution function (Option A immediate + Option D for opt-in merchants).
2. Backfill historical transactions with the corrected attribution.
3. Rerun the wash algorithm against the corrected inputs and publish the diff openly.

## 2. Realistic option set after CDP investigation

| Option | Accuracy | Coverage | Cost | When |
|---|---|---|---|---|
| **A. price-based** (seller, amount) | partial; ~25-50% within same-price bucket | universal | 1-line evm.py | **immediate** |
| **D. merchant feed** | 100% per adopting merchant | opt-in | merchant side: ~100 LoC; indexer: ~150 LoC | **Phase 2c** |
| **E. facilitator proxy** | 100% universal | requires merchants to route via our facilitator | new service + ops burden | Phase 3 (out of v2.1 scope) |

CDP/x402's missing settlement-log API is *the* finding that forces us toward
Option D over Option B. We can no longer claim "we observe the ecosystem from
the outside and reach 100%." Truthful position: **outside observation gets us
to ~25-50% accuracy on multi-endpoint sellers; the rest requires merchant
cooperation.** v2.1 ships both layers and is transparent about the limit.

## 3. Phase 2 sub-phases + dependencies

```
Phase 2a (done)
   └── CDP API mapping investigation → Option B killed
       │
Phase 2b — one-line evm.py fix (Option A-naive)
   │   Goal: stop the bleed. KR Crypto 11→4 buckets.
   │   Deliverable: oracle-patches/attribution-v2.1/evm_attribution_patch.py
   │   Verification: Moa runs idempotent patcher, restarts indexer,
   │                checks `services_with_seller(0xcF92)` distribution
   │                changes from {14391: 2451} to {14391: 1317, ...,
   │                14744: 546, ..., 14741: 537, ..., 14628: 17}.
   │
Phase 2c — merchant feed (Option D)
   │   Goal: KR Crypto attribution at 100%.
   │   Deliverables:
   │     - merchant_feed_spec.md (protocol spec)
   │     - merchant_feed_kr_crypto.py (KR Crypto side endpoint stub)
   │     - merchant_feed_indexer.py (x402watch side fetcher + DB writer)
   │   Verification:
   │     - x402watch fetches feed every hour
   │     - tx_hash match rate ≥ 99% vs KR Crypto stats.jsonl
   │
Phase 2d — backfill
   │   Goal: rewrite historical attribution from collapsed → correct.
   │   Deliverable: backfill_kr_crypto.sql
   │   Safety:
   │     - CREATE TABLE transactions_pre_v21_backup AS SELECT ...
   │     - Add attribution_source column ('legacy_collapse' /
   │       'price_match' / 'merchant_feed' / 'cdp_discovery')
   │     - Update rows in-place with new service_id + source
   │     - NEVER hard-delete; rollback = restore from backup table
   │   Verification:
   │     - Distribution by service_id matches expected from
   │       (price collisions partially) + (merchant feed exactly)
   │
Phase 2e — algorithm rerun
   │   Run:
   │     venv/bin/python -m indexer.categorize   (refreshes service_id-bound buyer_seller_labels)
   │     venv/bin/python -m indexer.derive_global (re-aggregates global buyer labels + service stats)
   │   Compare:
   │     - SELECT service_id, label, COUNT(*) FROM buyer_seller_labels GROUP BY 1,2
   │       pre vs post for #14391, KR Crypto siblings, Aubrai #14239
   │   Document the diff for the v2.1 transparency report.
   │
Phase 2f — v2.1 publication
       Goal: open-methodology promise kept.
       Deliverables:
         - content/methodology.md → §11 v2.1 changelog
         - content/announcements/v2.1-attribution-fix/
             twitter-thread.md, discord-message.md, github-release.md
       Tone: own the mistake plainly. KR Crypto's "96.4% → 0%" story now
       resolves to a more nuanced "partial false-positive removal +
       partial attribution-collapse artefact." Show before/after.
```

## 4. Hard invariants to preserve

| Invariant | How verified |
|---|---|
| PR #36 v2.3 X402ResourceRewriter still outermost | `curl -I /api/v1/health \| grep x-x402-rewriter` returns `v2.3` |
| 402 CORS triple intact | `curl -D - -o /dev/null .../wash-detail -H "Origin: ..."` |
| Tate's x402-surface-check returns 0 findings | run all 4 of his commands |
| Step 6 dispute system | `GET /api/disputes/buyer/{addr}` returns 200 |
| Step 4+5 alerts wireup | `tail var/stats.jsonl` shows `kind=mcp_call` with non-empty UA after a probe |
| Owner test payment still returns 200 | xpay.sh paywall live test against one paid endpoint |

If any invariant breaks during a Phase 2 step → rollback before continuing.

## 5. Risk register

| Risk | Mitigation |
|---|---|
| Backfill writes corrupt the canonical transactions table | `transactions_pre_v21_backup` taken first; `attribution_source` column lets us partition without delete |
| Algorithm rerun produces unflattering label changes for adopting merchants (KR Crypto loses kr-prices's 0% wash story) | Honest disclosure in v2.1 announcement; dispute system gives merchants recourse |
| Merchant feed Ed25519 signing gets misimplemented (replay attacks) | Spec includes nonce + monotonic `feed_seq` + cutoff window; indexer rejects feeds whose `feed_seq` is not strictly increasing |
| Non-x402 USDC transfers (CEX deposits etc.) still pollute attribution | Add `is_x402_payment` flag (default false); merchant feed sets it true; backfill marks legacy rows true for matched tx_hashes, false otherwise |
| Backfill stretches across multiple maintenance windows | Service pages can show a "v2.1 backfill in progress" banner driven by a `system_state` table row |

## 6. Decision points Moa owns before each phase

- **Before 2b**: confirm we want Option A-naive (lossy within same-price bucket) vs A-NULL (collision → NULL service_id, separate reattribute pipeline later).
- **Before 2c**: confirm KR Crypto merchant feed shape (we propose `/api/v1/x402watch-feed.json`, signed Ed25519 with the same key that signs payment receipts — or a separate ops key).
- **Before 2d**: choose backfill scope. KR Crypto only first? Or all top-20 multi-endpoint sellers in one pass?
- **Before 2e**: cutover window (production-affecting). Choose KST night/weekend.
- **Before 2f**: announcement tone. Strict honesty vs softened wording — current draft strict.

## 7. Out of v2.1 scope (Phase 3+)

- Facilitator proxy / operating our own x402 facilitator
- Solana indexer rewrite (currently 9 rows total — separate work item)
- Non-x402 USDC transfer noise filtering for non-KR sellers (we don't have ground truth feeds yet)
- CDP authenticated discovery (auth would only give us metadata we already have via unauth)

## 8. Phase 2b — pending P4 patch (resume after 2c + 2d)

`evm_attribution_patch.py` P1/P2/P3 are correct and verified, but
applying them alone regresses `index_chain`. The chain-indexer body
(evm.py ~L260-270) does:

```python
padded_sellers = [pad_topic_address(a) for a in seller_map.keys()]
```

After P1 the keys are `(addr, amount_micro)` tuples; `pad_topic_address`
calls `addr.lower()` → `AttributeError: 'tuple' object has no
attribute 'lower'`. The whole indexer crashes; Moa rolled back to
`evm.py.bak.attribution-v21-*` and the original indexer is running.

**P4 (to be added to the patcher):** the RPC log filter only needs the
distinct *addresses*, not the amount component. Change the seller-set
derivation to unpack the tuple key:

```python
# before
padded_sellers = [pad_topic_address(a) for a in seller_map.keys()]
# after
padded_sellers = [
    pad_topic_address(addr)
    for addr in {k[0] for k in seller_map.keys()}
]
```

The `{k[0] for k in seller_map.keys()}` set-comprehension also
deduplicates — a seller with 4 price tiers yields 4 map keys but only
one address to filter on, which is what we want.

P4 needs the exact evm.py:260-270 source to anchor on. Moa to paste
`sed -n '258,272p' indexer/evm.py` when Phase 2b resumes. Until then
Phase 2b stays rolled back; Phase 2c (merchant feed) and Phase 2d
(backfill) proceed independently — they write `transactions.service_id`
by tx_hash and never touch `evm.py`.
