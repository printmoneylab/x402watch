# x402watch — Wash-Filter Methodology

**Version:** v2.0 (2026-04-30)
**Status:** Production. Four-layer pipeline running daily on Oracle ARM (`indexer/seller_flags.py` → `indexer/pair_labels.py` → `indexer/derive_global.py`).
**Owner:** PrintMoneyLab
**Context:** x402 ecosystem analytics. We separate real demand from artificial / self-generated traffic and report it transparently per service.

**Core principle.** *Calling honest traffic fraudulent is worse than missing fraud.* We bias toward false negatives. Strong public labels (`suspected_wash`, `self_test`) require multiple independent signals and survive global-context guards. Anything below `confidence = 0.70` is shown as **unlabeled**.

---

## Changelog

- **v2.0 (2026-04-30) — four-layer redesign.** Replaced the single-pass global-buyer labeller with a four-layer pipeline: (1) per-seller flags, (2) per-(buyer, seller) pair labels, (3) multi-signal weighting with global guards, (4) global buyer labels derived from pair labels. Adds a 9th label `owner_test` for operator self-test traffic and excludes it from real-volume / suspected-wash denominators. Fixes the v1.x bug where a per-seller launch signal could label a single buyer `self_test` *globally*, blowing up `suspected_wash_pct` on unrelated services. Pre-redesign tables snapshotted to `*_pre_layer4_backup`; rollback path documented in `scripts/rollback_layer4.sh`.
- **v1.2 (2026-04-30):** Reclassified 5 weakest categories under v1.1 prompt; cross-LLM agreement settled at 78.9% on a fresh 199-sample stratified validation.
- **v1.1 (2026-04-30):** Added 4 seller-cohort wash-farm signals (uniform_amount, coordinated_start, uniform_tx_count, time_burst). Validated against aubr.ai (sybil farm) and KR Crypto (small-cohort self-test).
- **v1.0 (2026-04-29):** Initial 8-label taxonomy. Single-buyer signals only.

---

## 1. Quick reference — nine labels

Every (buyer, seller) pair gets exactly one of these labels. A buyer's *global* label is the tx-weighted majority across their pairs (see §3).

| Label | Read as | Counted in real volume? | Counted in suspected wash? |
|---|---|:---:|:---:|
| `organic_user` | Real human or unattributed real user | ✅ | — |
| `ai_agent` | LLM-driven multi-service consumer | ✅ | — |
| `exchange_user` | Buyer wallet IS a labelled CEX hot wallet | ✅ | — |
| `analytics_bot` | Periodic data-scraping bot | ✅ | — |
| `verifier` | Directory / discovery crawler | ✅ | — |
| `developer` | Backtest / load test on a single service | ❌ | — |
| `self_test` | Operator validating their own endpoint | ❌ | ✅ (flagged) |
| `suspected_wash` | Structural signals consistent with manufactured volume | ❌ | ✅ (flagged) |
| `owner_test` | Operator's own wallets (whitelist match) | ❌ (excluded from denominator) | — |

`real_volume_24h`, `real_volume_pct`, and `suspected_wash_pct` shown across the dashboard derive from these labels. `owner_test` traffic is excluded from the denominator entirely — it is operator self-test traffic that we can identify with certainty (whitelist match), so reporting it as either real or wash would distort honest service stats.

---

## 2. Why this exists

Public x402 dashboards (Coinbase Bazaar, x402scan) report raw transaction counts. For analytics this is a misleading headline number, because the same transaction counter responds identically to:

- A real user buying an inference call
- An operator pinging their own endpoint to validate it
- A directory crawler verifying every newly discovered service
- A backtesting script hammering one endpoint 600× in 10 minutes
- A wallet structure designed to inflate numbers for marketing

The first is value; the rest are noise of varying intent. Treating them as the same number flatters services with cheap noise sources and penalises services with quiet but real adoption. **x402watch's product wedge is filtering this noise honestly and methodically, and showing the methodology in the open.**

---

## 3. Four-layer architecture

```
   ┌────────────────────────────────────────────────────────────────┐
   │ Layer 1 — seller_flags   (per seller)                          │
   │   normal | suspicious_launch | confirmed_wash_farm | owner     │
   └─────────────────────┬──────────────────────────────────────────┘
                         │
   ┌─────────────────────▼──────────────────────────────────────────┐
   │ Layer 2 — pair_labels   (per (buyer, seller) pair)             │
   │   combines: seller flag + buyer global features + multi-signal │
   └─────────────────────┬──────────────────────────────────────────┘
                         │
   ┌─────────────────────▼──────────────────────────────────────────┐
   │ Layer 3 — global guards   (applied inside Layer 2)             │
   │   e.g. self_test caps out at 10 sellers; wash needs 20+/500+   │
   └─────────────────────┬──────────────────────────────────────────┘
                         │
   ┌─────────────────────▼──────────────────────────────────────────┐
   │ Layer 4 — derive_global   (per buyer; tx-weighted majority)    │
   │   + service-level rollup uses pair labels, not global label    │
   └────────────────────────────────────────────────────────────────┘
```

The 4-layer split solves a class of bugs that the v1.x single-pass labeller had no defence against: a signal that's true about a *seller* (e.g. "this seller's launch traffic was 95% from 2 wallets") was being attached to the *buyer* and then propagated to every other service that buyer touched. v2.0 keeps seller signals on the seller, buyer signals on the buyer, and only combines them inside a specific pair.

### Layer 1 — `seller_flags`

For every seller active in the last 30 days, we compute one flag from this priority chain:

1. **`owner_seller`** — seller wallet is in `data/owner_wallets.json` (operator self-disclosure). Short-circuits everything below.
2. **`confirmed_wash_farm`** — cohort signals fire affirmatively. Cohort ≥ 10 distinct buyers, *and* `uniform_amount_pct ≥ 0.80` *or* `coordinated_start_pct ≥ 0.70`, *and* `tx_count_cv ≤ 0.5`. The aubr.ai case (60-buyer cohort, uniform amount = 0.97, coordinated start = 0.88) is the canonical example.
3. **`suspicious_launch`** — within the first 7 days of a seller's `first_seen`, ≤ 3 distinct buyers cover ≥ 60% of services and the total span is ≤ 48h. This was *signal C* in v1.x — it now lives on the *seller*, where it belongs, instead of being projected onto every buyer in the cohort.
4. **`normal`** — no flag.

A seller's flag does *not* automatically label any buyer. It is one input to Layer 2.

### Layer 2 — `pair_labels`

For every (buyer, seller) pair active in the last 30 days, we compute a label by combining:

- The seller's Layer 1 flag.
- The buyer's global features (n_sellers, n_services, n_categories, vanity-cluster membership, inter-arrival gaps, wallet age).
- The pair's own features (n_tx for this seller, share of buyer's total tx, primary-seller share).

The pair label is the most specific label that fires, in this priority order:

1. `owner_test` — buyer or seller is in the owner whitelist.
2. `exchange_user` — buyer is in the CEX whitelist.
3. `suspected_wash` — seller flag is `confirmed_wash_farm` *and* the buyer's primary-seller share for this seller is ≥ 80% *and* (buyer is not vanity-distant *or* buyer fits the cohort tx-count median). **Global guard:** a buyer with `n_sellers ≥ 20` *and* `n_tx ≥ 500` is treated as too diversified for `suspected_wash` on a single seller pair, even if the seller is a wash farm. They are likely a real bot that happened to touch the farm; their pair label degrades to `developer` or `organic_user` depending on burst shape.
4. `self_test` — seller flag is `suspicious_launch` *and* the buyer is in the seller's small launch cohort. **Global guard:** a buyer with `n_sellers ≥ 10` *globally* cannot be `self_test` on any pair, because operator self-test traffic is by definition concentrated on the operator's own sellers. This guard is what stops the v1.x failure mode where a 151-seller `ai_agent` was labelled `self_test` everywhere.
5. `verifier` — buyer paid ≥ 100 distinct services across ≥ 20 distinct sellers, per-pair tx is 1-3, first-pair tx within 72h of seller's first_seen.
6. `analytics_bot` — wallet age > 30 days, gaps cluster on a periodic value, 1-5 services.
7. `ai_agent` — distinct categories ≥ 4, distinct sellers ≥ 5, per-tx amounts vary (CV > 0.3), active across ≥ 7 days.
8. `developer` — burst > 10 tx/min on a single service, ≥ 90% of pair tx on one service, payment span < 14 days.
9. `organic_user` — default when nothing above fires.

### Layer 3 — global guards (cross-cutting)

The guards inside Layer 2 are the heart of v2.0's false-positive controls. They look at the buyer's *global* shape before allowing a strong label on any single pair:

| Guard | Rule | Why |
|---|---|---|
| `SELF_TEST_MAX_GLOBAL_SELLERS = 10` | Buyer with ≥ 10 sellers globally cannot be `self_test` | Operators test their own sellers, not 10+ others |
| `WASH_DIVERSIFIED_MIN_SELLERS = 20` | Buyer with ≥ 20 sellers + ≥ 500 tx cannot be `suspected_wash` on a single pair | Real bots brush against wash farms; one pair doesn't make them wash |
| Vanity-cohort tx-count carve-out | A vanity-cluster member whose `n_tx ≥ 5× cohort median` keeps `self_test` (operator main wallet) instead of `suspected_wash` (sybil) | Distinguishes the operator from their sybil army |

### Layer 4 — `derive_global` and service rollups

The global buyer label is the **tx-weighted majority** label across that buyer's pairs. Ties are broken by tx-weighted average confidence. Owner buyers short-circuit to `owner_test`. The reason field lists the top three contributing labels with their tx-share (e.g. `derived_from_pairs:ai_agent(82%),developer(15%),organic_user(3%)`).

Service rollups (`real_volume_pct`, `suspected_wash_pct` in the `services` table) are computed from **pair labels**, not the buyer's global label. This is the second key v2.0 fix: under v1.x, a single global label per buyer was applied to every service they touched. Under v2.0, the same buyer can be `ai_agent` to service A and `developer` to service B, and each service sees the truthful per-pair share.

`owner_test` traffic is excluded from both numerator and denominator of the service rollup — it is neither demand nor fraud and shouldn't compress either percentage.

---

## 4. Confidence bands

Every label carries a confidence in `[0, 1]`. The dashboard renders three bands:

| Band | Confidence | UI rendering | Behaviour |
|---|---|---|---|
| **Strong** | `≥ 0.85` | Bold literal label (`ai_agent`) | Counted as the label in all stats |
| **Likely** | `0.70 – 0.84` | Softened label (`likely ai_agent`) + ⚠ link to this section | Counted as the label in stats, but visually softened so users understand it isn't certain |
| **Unknown** | `< 0.70` | `unlabeled` (italic, muted) | Treated as no-decision in the public UI |

Why these thresholds? Empirically, our pair-label confidence distribution is bimodal — clear cases cluster above 0.85 and clear non-cases below 0.50. The 0.70 floor is where the false-positive rate on hand-audited 30-buyer samples crosses ~5%, which is our public-display ceiling. The 0.85 line is where it crosses ~1%.

Owner-whitelisted labels (`owner_test`, `exchange_user`) bypass the soft band — they come from exact-match enumeration, so there is no confidence gradient to soften.

---

## 5. Known false-positive patterns

We list these openly because they're more useful disclosed than hidden:

- **AI agents touching wash farms.** A real LLM-driven user that happens to brush against a confirmed wash farm gets a `suspected_wash` label *on that pair*. Layer 3's diversified-buyer guard prevents this from contaminating their global label, but a service-level view will see the wash share on that one pair. Mitigation: filter the affected service's view, or rely on the buyer's per-pair confidence.
- **New legit services with small launch cohorts.** A service with 2-3 enthusiastic early adopters within its first 7 days fits the `suspicious_launch` seller pattern even if all 3 are genuine. Mitigation: this only escalates to a `self_test` pair label if the buyer also passes the cohort-membership signal. Single early adopters with broad activity elsewhere stay `organic_user`.
- **Operator-funded hot wallets we don't know about.** If an operator runs a hosted Render.com / Fly.io server with a wallet we haven't whitelisted, that server's traffic will look like a high-tx single-service buyer — typically `developer`, sometimes `self_test`. Mitigation: operator self-disclosure via the dispute mechanism (§6) adds the wallet to `data/owner_wallets.json`.
- **CEX withdrawal first-tx.** A real user who withdrew from a CEX yesterday won't match the CEX whitelist (because the buyer wallet is their personal address, not the exchange hot wallet). They'll label as `organic_user` — correct outcome, but `exchange_user` undercounts true exchange-funded demand. Phase 2 will follow funding hops.
- **The v1.x bug we just fixed.** Pre-v2.0, a 151-seller `ai_agent` (buyer `0x15C3…`) was globally labelled `self_test` because they happened to be in 31 sellers' launch cohorts. This compressed `real_volume_pct` on the 120 services where they were a legitimate user. v2.0's Layer 3 `SELF_TEST_MAX_GLOBAL_SELLERS = 10` guard is the structural fix.

---

## 6. Dispute process

Labels are public-facing numbers that move money (low `real_volume_pct` will lose marketing pull). Disputes are a first-class feature, not an afterthought:

- **Report-incorrect-label button** on `self_test` and `suspected_wash` badges. Opens an in-page dispute dialog that submits to `POST /api/disputes`. Required fields: a 32-1000 character reason; optional fields: your wallet address (for the audit log). A GitHub Issue link is kept as a secondary public channel inside the dialog footer.
- **Public API.**
  - `POST /api/disputes` — submit a dispute (rate-limited: 10 / IP / hour, 1 / IP / buyer / 24h, ≥ 50 / hour → 24h ban).
  - `GET /api/disputes/buyer/{address}` — public counts (`total`, `pending`, `reviewed`, `resolved`, `rejected`) so anyone can audit how often a wallet has been challenged.
- **Auto-recompute trigger.** When ≥ 5 independent reports pile up on one buyer, the buyer is added to `recompute_queue`. The next daily labeller run drains the queue, compares the new label to each dispute's snapshot, and closes the dispute as `resolved` (label changed) or `reviewed` (no change). Resolutions land in `label_disputes.resolution_note` for full traceability.
- **Operator whitelist intake.** If your dispute is "those are our own test wallets", send a signed message from the seller wallet so we can add it to `data/owner_wallets.json`. Verified wallets get the `owner_test` label permanently.
- **Re-evaluation cadence.** Daily labeller run picks up whitelist changes and processes the recompute queue within 24h. Backfill on demand if a dispute is time-sensitive.

We will not silently rewrite labels in response to disputes — every change is committed to the `buyer_labels` hypertable with an audit reason, the dispute carries its own row in `label_disputes`, and the changelog at the top of this document tracks methodology-level shifts.

---

## 7. Storage model

### `buyer_seller_labels` (Layer 2 output)

```sql
CREATE TABLE buyer_seller_labels (
    buyer_address  TEXT NOT NULL,
    seller_address TEXT NOT NULL,
    label          TEXT NOT NULL,
    confidence     NUMERIC(3,2),
    reason         TEXT,
    updated_at     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (buyer_address, seller_address)
);
```

### `seller_flags` (Layer 1 output)

```sql
CREATE TABLE seller_flags (
    seller_address TEXT PRIMARY KEY,
    flag           TEXT NOT NULL,   -- normal | suspicious_launch | confirmed_wash_farm | owner_seller
    cohort_size    INT,
    signals_json   JSONB,
    updated_at     TIMESTAMPTZ NOT NULL
);
```

### `buyer_labels` (Layer 4 output, TimescaleDB hypertable)

```sql
CREATE TABLE buyer_labels (
    time           TIMESTAMPTZ NOT NULL,
    buyer_address  TEXT        NOT NULL,
    label          TEXT        NOT NULL,
    confidence     NUMERIC(3,2),
    reason         TEXT,
    PRIMARY KEY (time, buyer_address)
);
SELECT create_hypertable('buyer_labels', 'time');
```

We write **only on label change** (or confidence shift ≥ 0.10). Most buyers' labels are stable across days; the hypertable stays small and historical reads stay fast.

### `label_disputes` and `recompute_queue` (Step 6)

```sql
CREATE TABLE label_disputes (
    id                 SERIAL PRIMARY KEY,
    buyer_address      TEXT NOT NULL,
    seller_address     TEXT,
    reporter_address   TEXT,
    reporter_ip        TEXT,
    reason             TEXT NOT NULL CHECK (char_length(reason) BETWEEN 32 AND 1000),
    current_label      TEXT NOT NULL,
    current_confidence NUMERIC(3,2),
    status             TEXT NOT NULL DEFAULT 'pending',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at        TIMESTAMPTZ,
    resolution_note    TEXT
);

CREATE TABLE recompute_queue (
    buyer_address TEXT PRIMARY KEY,
    triggered_by  INTEGER REFERENCES label_disputes(id) ON DELETE SET NULL,
    pending_count INTEGER NOT NULL DEFAULT 1,
    added_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at  TIMESTAMPTZ
);
```

A unique index `(buyer_address, COALESCE(reporter_address,''), COALESCE(reporter_ip,''), date_trunc('day', created_at))` enforces "one dispute per reporter per buyer per day" at the database layer, regardless of what the proxy did. The frontend's KV rate limiter is a fast filter; the DB index is the source of truth.

### Service rollups in `services`

```sql
organic_traffic_pct  NUMERIC(5,2),  -- real / (total − owner_test)
suspected_wash_pct   NUMERIC(5,2),  -- wash / (total − owner_test)
metadata             JSONB,         -- developer_volume_pct, owner_test_tx
last_label_calc      TIMESTAMPTZ
```

### Recompute schedule

Daily at KST 09:00 (UTC 00:00) via systemd timer on the Oracle ARM box. The full v2.0 pipeline (seller_flags → pair_labels → derive_global → service rollups) currently runs in ~25 seconds for ~5,400 pairs and ~1,000 sellers.

---

## 8. Academic grounding

- **Cong, Li, Tang, Yang (2023)** — *"Crypto Wash Trading"*, *Management Science* 69(11): 6427–6454. Establishes the ~70% wash-trade share on unregulated CEXes via Benford-law and trade-size rounding tests; provides the statistical playbook for amount-pattern signals.
- **Victor & Weintraud (2021)** — *"Detecting and Quantifying Wash Trading on Decentralized Cryptocurrency Exchanges"*, WWW '21. arXiv:2102.07001. Directed-graph cycle detection — the basis for our graph-cycle suspect signal.
- **Ramos & Zanko (2020)** — *"A review on cryptocurrency transaction methods for money laundering"*, J. Money Laundering Control 23(4). Funding-graph heuristics for sybil detection.
- **Aspris, Foley, Svec, Wang (2021)** — *"Decentralized exchanges: The 'wild west' of cryptocurrency trading"*, Int. Rev. Financial Analysis 77. Empirical baseline rates of wash trading used to sanity-check our thresholds.

---

## 9. Open questions / known limitations

1. **Cross-chain identity.** Same operator, different wallets per chain. Each chain is currently independent. Phase 2 may use ENS / Coinbase Smart Wallet linking.
2. **CEX whitelist on Base/Arbitrum.** Public sources are sparse. We seed `data/exchange_wallets.json` from known hot wallets and expand opportunistically.
3. **`ai_agent` vs `organic_user` boundary.** Both are real-volume-positive, so the split matters less for headline numbers than for category-mix reporting.
4. **Suspected_wash without graph features.** v2.0 ships without NetworkX cycle detection at scale; only structural cohort signals are wired into Layer 1. Cycle detection is a follow-up.
5. **Solana labelling lag.** Solana addresses aren't hex; the vanity-cluster prefix/suffix heuristics from v1.x EVM logic are disabled on Solana pairs pending a base58-aware reimplementation.

---

## 10. Phase 2 roadmap

Items the v2.0 ship deliberately left for later:

1. **Buyer profile pages** (`/buyers/{address}`) — global label + confidence + per-pair breakdown table + dispute count. Needs a new public `GET /api/v1/buyers/{address}` endpoint on Oracle that joins `buyer_labels` + `buyer_seller_labels` + `label_disputes`. UI is straightforward once the endpoint lands.
2. **Admin disputes dashboard** (`/admin/disputes`) — moderation UI in front of `GET /api/v1/internal/disputes/list`. Status transitions (`pending → reviewed/resolved/rejected`) with a resolution_note input.
3. **Wallet-signed dispute attribution.** Today a reporter wallet is supplied freely. Phase 2 challenges the reporter to sign a nonce so dispute authorship is verifiable on-chain and `data/owner_wallets.json` self-service adds become possible.
4. **Cross-chain identity linking** — ENS / CB Smart Wallet to merge per-chain buyer rows into a single global profile.
5. **Solana vanity heuristics** — base58-aware prefix/suffix tier so Solana pairs get the same Layer 1 / Layer 2 treatment as EVM pairs.
6. **NetworkX cycle detection at scale.** v2.0 ships without it; pre-compute per-seller subgraphs once a day rather than at query time.
7. **Dispute-driven algorithm tuning.** When a buyer accumulates ≥ N `resolved` (label-changed) disputes against the *same* `current_label`, that's a signal the algorithm has a systematic bias for that label. Track and surface in the methodology changelog.

Phase 2 work is *non-blocking* for the v2.0 announcement — the algorithm and dispute submission already work end-to-end.

---

## Appendix A. v1.x signal reference (historical)

The signals below are the per-buyer heuristics from v1.0 / v1.1. Most are subsumed into Layer 1 seller flags or Layer 2 buyer features in v2.0. Documented here so that older changelogs, GitHub issues, and external citations remain interpretable.

### Vanity clustering (v1.x) — two tiers

| Tier | prefix len | suffix len | min cluster size | Pattern caught |
|---|:---:|:---:|:---:|---|
| `strict` | 4 hex | 3 hex | 3+ | orbisapi-style farmed wallets (`0x07b0...c0d` ×17) |
| `broad`  | 2 hex | 3 hex | 4+ | KR Crypto-style short vanity (`0x29...725` ×6) |

A buyer in **both** tiers gets the strongest base confidence (0.95). Strict-only maps to 0.90, broad-only to 0.60. In v2.0 these tiers feed Layer 2's vanity-cohort tx-count carve-out.

### Self-test signals A/B/C/D (v1.x)

- **Signal A** — vanity cluster + single-service concentration. *In v2.0:* fed into Layer 1 `suspicious_launch` + Layer 2 pair logic.
- **Signal B** — vanity cluster + single transaction. *In v2.0:* Layer 2 cohort-membership.
- **Signal C** — launch-window concentration (≤ 3 distinct buyers covering ≥ 60% of services within 48h of `first_seen`). *In v2.0:* now lives entirely on the **seller** as the `suspicious_launch` flag. This is the v1.x → v2.0 architectural fix.
- **Signal D** — funding-source equality. Deferred (requires off-chain RPC traversal).

### Seller-cohort signals (v1.1)

| Signal | Definition | Threshold |
|---|---|---:|
| `cohort_size` | distinct buyers paying this seller in 30d | `≥ 10` |
| `uniform_amount_pct` | share of cohort whose median amount equals seller's modal amount | `≥ 80%` |
| `coordinated_start_pct` | max share of buyers whose first-tx falls in any single 30-min window | `≥ 70%` |
| `uniform_tx_count_cv` | stddev/avg of tx counts across the cohort | `≤ 0.5` |

**Wash-farm rule (v1.1, unchanged in v2.0):** `cohort_size ≥ 10 AND (uniform_amount OR coordinated_start) AND uniform_tx_count`. In v2.0 these feed Layer 1's `confirmed_wash_farm` flag.

### Validation cases (v1.1 → v2.0)

| Pattern | aubr.ai | KR Crypto | orbisapi |
|---|---|---|---|
| `cohort_size` | 60 | 8 | 71 |
| `uniform_amount_pct` | 0.97 | 0.20 | mixed |
| `coordinated_start_pct` | 0.88 | 0.10 | low |
| `uniform_tx_count_cv` | 0.23 | high | high |
| v1.1 seller verdict | wash farm | (cohort < 10) | (cv high) |
| v2.0 Layer 1 flag | `confirmed_wash_farm` | `suspicious_launch` | `suspicious_launch` |
| v2.0 final labels | 59 → `suspected_wash`, 1 → `self_test` | 8 → `self_test` | 17 vanity → `self_test`, 3 high-burst → `developer`, rest mixed |

---

*Last updated: 2026-04-30. Methodology owner: PrintMoneyLab. Disputes: GitHub Issues under `dispute` / `label-review` labels.*
