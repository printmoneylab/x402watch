# x402watch — Wash-Filter Methodology

**Version:** v1.1 (Day 9, 2026-04-30)
**Status:** Phase 1 in production (`indexer/labeller.py`, daily systemd timer at KST 09:30).
**Owner:** PrintMoneyLab
**Context:** x402 ecosystem analytics. We separate "real demand" from artificial / self-generated traffic and report it transparently per service.

**Changelog**
- **v1.2 (2026-04-30, afternoon):** Reclassified 5 worst-performing categories (`search_engine`, `storage`, `news`, `okr_productivity`, `media_database`) under v1.1 prompt. End-state cross-LLM agreement settled at **78.9%** on a fresh 199-sample stratified validation. The post-reclassify number is *lower* than v1.1's 81.4% peak because Sonnet-4.5's stricter v1.1 prompt now routes more services to `other` for the categories that *weren't* re-classified (notably `authentication`, `content_generation`, `blockchain_infra`); achieving an 85%+ ceiling requires a full ~12,500-distinct re-classification with v1.1 prompt (~$2 spend) — deferred. Stable headline accuracy: **~80% Haiku-vs-Sonnet agreement on substantive categories**.
- **v1.1 (2026-04-30, morning):** Added 4 seller-cohort wash-farm signals (uniform_amount, coordinated_start, uniform_tx_count, time_burst). Sharpened the self_test vs suspected_wash boundary by cohort size. Validated against aubr.ai (sybil farm) and KR Crypto (small-cohort self-test) on production data. Category-classification prompt tightened on weak boundaries (media_database vs entertainment_media, content_generation vs ai_inference, agent_payments vs defi_data, business_intelligence vs scientific_data); cross-LLM agreement rose from 73.9% to 81.4% on 200 stratified samples (Haiku 4.5 vs Sonnet 4.5 reference).
- **v1.0 (2026-04-29):** Initial 8-label taxonomy. Single-buyer signals only. Production deployment.

## Category-classification accuracy (Haiku 4.5 production, Sonnet 4.5 reference)

| Round | Prompt version | Sample size | Overall agreement | Strongest categories | Weakest categories |
|---|---|---:|---:|---|---|
| 1 (Day 9) | v1.0 | 199 | 73.9% | financial_data, e_commerce, transport_logistics (100%) | media_database, agent_payments (0%); content_generation, agent_communication (25%) |
| 2 (Day 9) | v1.1 (4 boundary clarifications) | 199 | **81.4%** | business_intelligence, ai_inference, entertainment_media (100%) | search_engine (0%) — Sonnet now routes to `other` |
| 3 (Day 10) | v1.1 + 5 weak categories re-classified | 199 | 78.9% | okr_productivity, wallet_analytics, e_commerce, agent_payments, token_safety (100%) | authentication (14%), search_engine, storage (25%) |

**Weakest categories shared across rounds**: `search_engine`, `storage`, `news`, `authentication`. These represent real category-boundary ambiguity that the prompt alone can't fully fix; humans would also disagree on edge cases. Phase 2 will explore (a) reclassifying *all* services under v1.1 prompt for symmetric measurement, and (b) consolidating overlapping categories where appropriate (e.g. `search_engine` ↔ `ai_search`).

**Publishable headline**: *"AI category classification: ~80% cross-LLM agreement on substantive categories (Haiku 4.5 vs Sonnet 4.5 reference; n=199 stratified). Weakest categories surfaced and listed for transparency."*

---

## 1. Why this exists

Public x402 dashboards (Coinbase Bazaar, x402scan) report raw transaction counts.
For analytics this is a misleading headline number, because the same transaction
counter responds identically to:

- A real user buying an inference call
- An operator pinging their own endpoint to validate it
- A directory crawler verifying every newly discovered service
- A backtesting script hammering one endpoint 600× in 10 minutes
- A wallet structure designed to inflate numbers for marketing

The first is value; the rest are noise of varying intent. Treating them as the
same number flatters services with cheap noise sources and penalises services
with quiet but real adoption. **x402watch's product wedge is filtering this
noise honestly and methodically, and showing the methodology in the open.**

---

## 2. Eight-label taxonomy

Every observed buyer wallet is assigned exactly one label per labelling run.
Labels are *time-versioned*: only changes are persisted (see §5). Labels are
mutually exclusive — a wallet that exhibits multiple signals is assigned the
**most specific** label per the priority order below.

**Effective evaluation order in code** (Phase 1):
`exchange_user → self_test → verifier → analytics_bot → ai_agent → developer`,
then check `suspected_wash` signals (must fire affirmatively to take effect),
finally default to `organic_user`. So `suspected_wash` is the "specific flag
that overrides organic when signals fire", not a pure fallback.

| Label              | Eval order | Heuristic centre of gravity | Counted in real-volume? |
|--------------------|:---------:|------------------------------|:-----------------------:|
| `exchange_user`    | 1 | Buyer wallet IS a labelled CEX hot wallet | yes (real demand) |
| `self_test`        | 2 | Operator's own endpoint validation traffic | **no** |
| `verifier`         | 3 | Directory / discovery crawler | **no** |
| `analytics_bot`    | 4 | Periodic data-scraping bot | partial (configurable) |
| `developer`        | 5 | Single-service heavy bot / backtest | **no** |
| `ai_agent`         | 6 | LLM-driven multi-service consumer | yes |
| `suspected_wash`   | 7 | Wash-shaped signals (uniform amount + short window, or graph cycle) | **no, flagged** |
| `organic_user`     | 8 | None of the above signals are strong | yes |

`real_volume_24h` and `organic_traffic_pct` (in `services` and `category_stats`)
exclude `self_test`, `verifier`, `developer`, and `suspected_wash` by default,
and partially exclude `analytics_bot` per a per-service heuristic. Service-level
roll-ups also write `metadata.developer_volume_pct` so the developer share is
visible without being counted as real demand.

---

## 3. Detection signals per label

Each label is decided by a small set of signals. **Confidence** in `[0, 1]` is
the proportion of triggering signals weighted by their reliability. We persist
the human-readable `reason` so audit and operator dispute is easy.

### 3.1 `exchange_user`

Match `buyer_address` against `data/exchange_wallets.json`. Direct match → label
with `confidence = 1.0`.

Signals:
1. Direct match in CEX whitelist (sufficient).
2. (Phase 2, requires upstream RPC) Funded ≤ 2 hops from a CEX whitelist wallet
   within 30 days, no other labels triggered.

Failure mode: A real user *withdrew from CEX yesterday* will not match unless
we expand to upstream funding. Acceptable at Phase 1.

### 3.2 `self_test` *(highest-leverage label — see §4)*

The "operator validating their own endpoints" pattern. KR Crypto's launch is
the canonical example. **Phase 1 implementation evaluates four named signals
A/B/C/D and assigns the label if any is satisfied.** Confidence reflects
signal strength.

#### Signal A — vanity cluster + single-service concentration
Buyer is a member of a per-seller vanity cluster *and* paid only one service.
Strong indicator that a vanity-mined wallet was used to pad a specific
service's launch traffic.
- **Confidence:** 0.62–0.97 depending on the vanity tier (see below).

#### Signal B — vanity cluster + single transaction
Buyer is a vanity-cluster member with `n_tx == 1` and a tiny amount. This
catches the "fire-once-and-forget" wallets seen in the KR Crypto cohort that
the previous prototype missed.
- **Confidence:** 0.66 (broad-vanity) to 1.00 (strict-vanity).

#### Signal C — launch-window concentration
Within the first 7 days of a seller's first service `first_seen`:
the seller's distinct-buyer count is `≤ 3`, this buyer covered `≥ 60%` of the
seller's services, and total span `≤ 48h`. Captures the classic "operator
hammers their own endpoints right after launch" pattern, even without vanity
addresses.
- **Confidence:** 0.80.

#### Signal D — funding-source equality *(deferred to Phase 2)*
Buyer's funding source (1–2 hops upstream) equals the seller's wallet (or a
related operator wallet). Requires off-chain RPC traversal of buyer funding
history; not implemented in Phase 1 because we only index x402 inflows, not
buyer-side balance histories.

#### Vanity clustering — two tiers (Day 7 recommendation #1)

| Tier | prefix len | suffix len | min cluster size | Pattern caught |
|---|:---:|:---:|:---:|---|
| `strict` | 4 hex | 3 hex | 3+ | orbisapi-style farmed wallets (`0x07b0...c0d` ×17) |
| `broad`  | 2 hex | 3 hex | 4+ | KR Crypto-style short vanity (`0x29...725` ×6) |

A buyer in **both** tiers gets the strongest base confidence (0.95). Strict-only
maps to 0.90, broad-only to 0.60.

#### False-positive controls
- Signal C requires a small-cohort *seller* (`≤ 3` first-7d distinct buyers),
  so a single early adopter on a successful launch will not match.
- Vanity signals require `min_cluster_size ≥ 3` (strict) or `≥ 4` (broad);
  collisions by chance at these thresholds are vanishingly rare for random
  addresses (`(1/16^7)^3 ≈ 4×10^-25` per coincidence).
- A buyer matching Signal C *but* with broad activity (e.g., 100+ services
  paid system-wide) is a known limitation: they get globally labelled
  `self_test` even when their main role looks like `ai_agent`. Phase 1 accepts
  this conservative bias; Phase 2 may scope Signal C per-seller instead of
  per-buyer.

### 3.3 `verifier`

Directory / crawler bots like x402scan that validate every newly listed service.

Signals (any 3 of 5):
1. Buyer paid `≥ 100` distinct services across `≥ 20` distinct sellers within
   30 days. (Threshold tuned to current ecosystem; will rise with growth.)
2. Per-service tx count is consistently `1–3` (sample-once-then-leave).
3. First payment to a new service occurs within `< 72 hours` of that service's
   `first_seen`.
4. Inter-tx gap distribution is heavy-tailed and machine-like (long pauses,
   then short bursts during indexing windows).
5. Wallet has **no concentrated sub-ecosystem** — never spends `> 5%` of total
   tx on any single service.

### 3.4 `analytics_bot`

Periodic data-scraping bot — typically a long-lived wallet, fixed cadence.

Signals (any 3 of 5):
1. Buyer's first activity on x402 is `> 30 days` before the labelling run.
2. Per-service inter-tx gaps cluster on a single periodic value (every 5 min,
   every hour, every 4 hours) within `±10%` jitter.
3. Concentrated on `1–5` services (data-source endpoints).
4. Volume profile is steady (CV of daily tx count `< 0.4`).
5. Median amount equals service `price_amount` exactly (no rounding errors,
   suggests programmatic billing).

Distinguished from `developer` by **wallet age** and **steady cadence** (not
bursty).

### 3.5 `developer`

Backtest, load test, or paid-for-once-then-forgotten debug session.

Signals (any 3 of 5):
1. Burst rate `> 10 tx/minute` for any 60-minute window on a single service.
2. `≥ 90%` of buyer's tx fall on **one service**.
3. Payment span `< 14 days` total.
4. Wallet age (first_seen on x402) `< 14 days` at peak burst.
5. After burst ends, tx rate drops to near-zero and stays there.

### 3.6 `ai_agent`

LLM-driven users who hit a varied set of services per task.

Signals (any 3 of 5):
1. Distinct service categories `≥ 4` across the wallet's history.
2. Distinct sellers `≥ 5`.
3. Per-tx amounts vary (CV `> 0.3`); not a fixed rate.
4. Inter-tx gap distribution has a heavy short-tail (sub-second clusters during
   an LLM's tool-use bursts).
5. Wallet is *active*: uses x402 across multiple separate sessions over `≥ 7`
   days.

This label is **revenue-positive** for x402 services and is counted in real
volume.

### 3.7 `organic_user`

Catch-all for buyers showing no strong signal of any other label *and* meeting
basic plausibility:

- Wallet age `> 24 hours` at first x402 tx.
- Total tx `≥ 2` (single-tx buyers go to `suspected_wash` only if other signals
  fire; otherwise `organic_user`).
- No vanity address pattern in their cohort.

`organic_user` is the default — better to over-include here than to mis-label
and depress a service's reported real volume. Operator dispute mechanism
(Phase 1) lets us recover from false negatives elsewhere.

### 3.8 `suspected_wash`

Reserved for buyers exhibiting structural signals consistent with manufactured
volume but *not* fitting the operator-self-test pattern. Phase 1 evaluates two
families of signals: **single-buyer signals** (legacy) and **seller-cohort
signals** (new in v1.1).

#### 3.8a Single-buyer signals (legacy)

A non-vanity buyer with all of:
- Single-service concentration (`n_services == 1`, `n_tx ≥ 5`).
- Activity span `< 3 days`.
- Amount uniformity: `(max - min) / avg < 5%`.

Plus optional graph-cycle participation (NetworkX `simple_cycles`). Phase 1
cycle detection has limited reach because we only index x402 inflows; Phase 2
will add seller outflow indexing for true round-trip detection.

#### 3.8b Seller-cohort signals (v1.1) — **the heart of v1.1**

Computed once per seller over the last 30 days; if a seller is flagged as a
**wash farm**, its non-vanity buyers (with `primary_seller_share ≥ 80%`) get
labelled `suspected_wash` with high confidence.

| Signal | Definition | Threshold for fire |
|---|---|---:|
| `cohort_size` | distinct buyers paying this seller in 30d | `≥ 10` |
| `uniform_amount_pct` | share of cohort buyers whose median amount equals the seller's modal amount | `≥ 80%` |
| `coordinated_start_pct` | max share of buyers whose first-tx falls in any single 30-min window | `≥ 70%` |
| `uniform_tx_count_cv` | stddev/avg of tx counts across the cohort | `≤ 0.5` |

**Wash-farm rule:** `cohort_size ≥ 10 AND (uniform_amount OR coordinated_start) AND uniform_tx_count`.
A confidence boost is awarded for a 4th signal: `cohort_size ≥ 20`.

#### 3.8c Vanity-cluster reclassification under v1.1

A buyer who is in a vanity cluster *and* whose primary seller is a wash farm
*and* the cohort is large (`≥ 10`) is reclassified from `self_test` to
`suspected_wash` (sybil-farm member), with one carve-out: if the buyer's
`n_tx ≥ 5×` the cohort's median, treat them as the *operator's* main wallet
and keep the `self_test` label. This lets us distinguish the operator from
the army of sybil wallets they minted.

#### 3.8d Validation case differences

| Pattern | aubr.ai | KR Crypto | orbisapi |
|---|---|---|---|
| `cohort_size` | 60 | 8 | 71 |
| `uniform_amount_pct` | 0.97 | 0.20 | mixed |
| `coordinated_start_pct` | 0.88 (12:30-13:00 4/28) | 0.10 (multi-day) | low |
| `uniform_tx_count_cv` | 0.23 | high | high |
| **wash-farm verdict** | **YES** | NO (cohort < 10) | NO (CV high) |
| Vanity strict cluster | none | none | 17 buyers `0x07b0..c0d` |
| Vanity broad cluster | none | 6 buyers `0x29..725` | n/a |
| **Final labels** | 59/60 → `suspected_wash`, 1 → `self_test` (operator) | 8/8 → `self_test` | 17 vanity → `self_test`, 3 high-burst → `developer`, rest mixed |
| **Confidence** | 0.90 | 0.62–0.80 | 0.62–0.97 |

KR Crypto and orbisapi are correctly *kept* as self-test even after v1.1 because
their cohort signatures are not coordinated farms (varied amounts, varied
timing, high tx_count CV). aubr.ai is correctly *upgraded* from a noisy
single-buyer label to high-confidence cohort-driven `suspected_wash`.

---

## 4. Self-test detection in detail

This is the highest-leverage detection because:
- It captures the *most common* form of inflated traffic in early x402.
- It's the most defensible to surface: "operator validating their own service"
  is a benign behaviour we can label without accusing anyone.
- The signals are clean and the false-positive cost is low (organic users on a
  brand-new service look little like a saturated self-test).

### Algorithm

```
for each (seller, service) launched in the last 30 days:
    buyers_in_first_7d = SELECT DISTINCT buyer FROM transactions
                          WHERE service_id IN (seller's services)
                            AND time BETWEEN service.first_seen
                                         AND service.first_seen + INTERVAL '7 days'
    if len(buyers_in_first_7d) > 3:
        skip   # too many distinct buyers — not a self-test pattern

    for buyer in buyers_in_first_7d:
        signals = {
            'first_7d_concentration':
                buyer accounts for > 60% of first-7d tx for any one service,
            'cross_service':
                buyer paid >= 60% of seller's distinct services,
            'time_concentrated':
                median inter-tx < 60s AND p90 span < 48h,
            'sharp_decay':
                > 80% of buyer's seller-tx in first 72h,
            'vanity_pattern':
                shares 6+ char prefix or suffix with >=3 other buyers
                of the same seller,
            'price_minimum':
                avg amount <= 1.2× lowest price across seller's services,
        }
        if sum(signals.values()) >= 4:
            label(buyer, 'self_test',
                  confidence=sum/6,
                  reason=','.join(k for k,v in signals.items() if v))
```

### Validation case — KR Crypto

Five buyer addresses observed against KR Crypto's wallet share the structural
prefix `0x29` and suffix `725`:

```
0x2914...8c315be174ef40dc962d79725  — 33 tx (high-volume "Render.com" candidate)
0x2915ad...aebb3885c4971c155178c7fb17ebb725
0x29195555...e044fc7230e623791e64df68da2ea725
0x2919b6...83822c05ffbe31240485165525380e9725
0x291fe7...9ce24a81af44024c3afc90e68ae29ad725
0x291028...aff1a940096be6f66dda10c4be8f687725
```

Five wallets sharing both a 4-char prefix AND a 3-char suffix is exceedingly
unlikely by chance (probability `(1/16)^14 ≈ 5×10^-18` per pair, much higher
when the wallets are vanity-mined to spec). The vanity_pattern signal alone
warrants flagging; combined with single-service-each + tiny-amount + within-
launch-window, all five clear the 4-of-6 threshold.

The `0x2914...725` wallet (33 tx, $1.10) is the **outlier** that needs careful
treatment: it might be the operator's *primary* test wallet (prolonged usage),
*or* it might be an externally hosted server (e.g., Render.com) that the
operator pre-paid for and which then runs continuously. Distinguishing requires
operator self-disclosure in Phase 1; until then it labels as `self_test` and
the operator can dispute.

---

## 5. Storage model

### `buyer_labels` (TimescaleDB hypertable)

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

We write **only on label change**, not every recompute. This keeps the table
small (most buyers' labels are stable across days) and gives a clean
historical read: "what was this buyer's label on date X?" → most-recent row
where `time ≤ X`.

### Service rollups in `services`

```sql
ALTER TABLE services
    ADD COLUMN organic_traffic_pct NUMERIC(5,2),
    ADD COLUMN suspected_wash_pct  NUMERIC(5,2),
    ADD COLUMN last_label_calc     TIMESTAMPTZ;
```

`organic_traffic_pct` is the share of the service's last-30-day tx coming from
buyers whose **current** label is `exchange_user`, `ai_agent`, or `organic_user`.
`suspected_wash_pct` is the share from `suspected_wash`. Other labels
(self_test / verifier / developer / analytics_bot) are excluded from both
percentages by design — they are neither real demand nor manufactured fraud,
just a category we set aside.

### Recompute schedule

`Daily at KST 09:00` (UTC 00:00). Triggered by a systemd timer.

The labeller iterates buyers active in the last 30 days, computes the signal
vector, and:
1. Writes a new `buyer_labels` row only when the label or `(confidence, reason)`
   pair changes meaningfully (we treat reason changes as informational and
   require a full label transition or `confidence` shift `≥ 0.2` to write).
2. Recomputes `services.{organic_traffic_pct, suspected_wash_pct,
   last_label_calc}` for every active service.

---

## 6. False-positive handling

Wash-filter labels are **public-facing** numbers that can move money (services
with low organic_traffic_pct will lose marketing pull). We treat false
positives as a first-class concern:

- **No accusatory labels in the public UI for low-confidence verdicts.**
  `suspected_wash` is shown only when `confidence ≥ 0.7`. Below that, the
  buyer is labelled `organic_user` and the signal is logged internally for
  ongoing tuning.
- **Operator dispute mechanism (Phase 1).** A service operator who claims they
  are not self-testing can submit a wallet for re-evaluation. We will not
  reverse the label, but we'll surface their claim alongside ours and give
  them a per-service "operator disputes" pill in the UI.
- **Wallet-cluster overrides.** A short editorial whitelist for wallets we
  know are legitimate via off-chain signals (e.g., a service's verified
  Render.com server). Stored in `data/buyer_overrides.json`; precedence over
  algorithmic labels.
- **Conservative defaults.** When in doubt, label `organic_user` rather than
  `suspected_wash`. Better to under-flag than over-flag publicly.

---

## 7. Academic grounding

The taxonomy and the cycle-detection approach to wash trading draw from:

- **Cong, Li, Tang, Yang (2023)** — *"Crypto Wash Trading"*, *Management
  Science* 69(11): 6427–6454. DOI 10.1287/mnsc.2023.4869. Establishes the
  ~70% wash-trade share on unregulated CEXes via Benford-law and trade-size
  rounding tests; provides the statistical playbook for §3.8 amount-pattern
  signals.

- **Victor & Weintraud (2021)** — *"Detecting and Quantifying Wash Trading on
  Decentralized Cryptocurrency Exchanges"*, WWW '21. arXiv:2102.07001.
  Introduces the directed-graph cycle detection approach we implement in
  Week 2: build a buyer→seller transfer graph over a window, run
  `simple_cycles` to surface round-trip flows, score by cycle length and
  amount-uniformity. Establishes the wallet-cluster heuristics we adapt for
  §3.8 funding-correlation signals.

- **Ramos & Zanko (2020)** — *"A review on cryptocurrency transaction
  methods for money laundering"*, J. Money Laundering Control 23(4).
  Background on funding-graph heuristics for sybil and wash detection.

- **Aspris, Foley, Svec, Wang (2021)** — *"Decentralized exchanges: The
  'wild west' of cryptocurrency trading"*, Int. Rev. Financial Analysis 77.
  Provides the empirical baseline rates of wash trading we use to sanity-
  check our detection thresholds (avoid both over- and under-flagging).

---

## 8. Open questions / known limitations

1. **Cross-chain identity.** Same operator, different wallets per chain. We
   currently treat each chain independently. Phase 2 may use ENS / Coinbase
   Smart Wallet linking.
2. **CEX whitelist on Base/Arbitrum.** Public sources are sparse; users must
   populate `data/exchange_wallets.json` with chain-specific entries.
3. **`ai_agent` vs `organic_user` boundary.** Both are positive-counted, so
   the split matters less for headline numbers than for category-mix
   reporting. We may collapse them in v1.
4. **Label persistence vs re-labelling.** A wallet labelled `developer` during
   a backtest burst should not stay labelled `developer` forever once their
   activity changes shape. The daily recompute handles this — we just need to
   ensure label transitions are surfaced rather than silently overwritten.
5. **Suspected_wash without graph features.** Phase 1 ships without
   NetworkX cycle detection (signal 1 and 6 in §3.8); only structural signals
   2/3/4/5 are available. Cycle detection arrives Week 2.

---

*Last updated: 2026-04-30. Methodology owner: PrintMoneyLab. Disputes welcome
in operator Telegram or via the Phase-1 dispute form.*
