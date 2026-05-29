#!/usr/bin/env python3
"""
P1 fix — reconcile x402watch attribution from stats.jsonl tx_hash.

The EVM indexer keys services attribution by (seller_address, amount_micro),
so when multiple services share the same (seller, amount) the MIN(id) wins
and other services' payments are absorbed into the wrong row. This script
uses the authoritative pairing exposed by the 2026-05-29 P3 fix —
stats.jsonl payment events carry tx_hash + endpoint together — to
re-attribute affected transactions row by tx_hash.

What it does
============
For each `kind=payment` event in stats.jsonl that has a tx_hash:
  1. Look up the canonical service_id from the endpoint path
     (one of 5 x402watch templates, matched against the concrete
     `{address}` / `{service_id}` / `{slug}` placeholders).
  2. Verify the stats.jsonl amount_usd matches the canonical price for
     that service_id (5% tolerance). Mismatch → skip + log.
  3. Look up the transactions row by tx_hash.
  4. If service_id is already correct → no-op (idempotent).
  5. Otherwise UPDATE transactions SET service_id, attribution_source =
     'x402watch_reconcile', is_x402_payment = TRUE WHERE tx_hash = $1.

What it does NOT do
===================
- No DELETE / no INSERT — UPDATE only on existing rows.
- No touch on the EVM indexer or services tables.
- Endpoints outside the 5-template allowlist → skipped (regression-safe).
- P3-era events with tx_hash=NULL → skipped (un-reconcilable; documented).

Idempotency
===========
- already-correct rows → already_correct counter, no UPDATE.
- already-tagged with `attribution_source='x402watch_reconcile'` → if
  the service_id also matches, no-op. If the service_id has drifted
  back (shouldn't happen, but defensive) → re-applied cleanly.

Usage
=====
  venv/bin/python scripts/reconcile_x402watch_attribution.py --self-test
  venv/bin/python scripts/reconcile_x402watch_attribution.py
  venv/bin/python scripts/reconcile_x402watch_attribution.py --apply
  venv/bin/python scripts/reconcile_x402watch_attribution.py --apply \
      --since 2026-05-29T19:56:00+09:00

cron / systemd timer suitable for hourly runs — see RECONCILE_DEPLOY.md.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


log = logging.getLogger(__name__)


# ─── 5 x402watch endpoint → service_id mapping (the bug surface) ─────
ENDPOINT_TO_SERVICE_ID: dict[str, int] = {
    "/api/v1/services/{service_id}/wash-detail":   3268993,
    "/api/v1/wash/check":                          7604654,
    "/api/v1/categories/{slug}/full-history":      7604655,
    "/api/v1/services/{service_id}/transactions":  7604656,
    "/api/v1/buyers/{address}/profile":            7604657,
}

# Canonical USD price for each service — used to verify the
# stats.jsonl amount before re-attributing. Treat a mismatch as a
# signal that the event is NOT one of these 5 endpoints (someone else's
# payment, or a price change we don't know about) and skip rather than
# risk wrong-attributing.
SERVICE_PRICE_USD: dict[int, float] = {
    3268993: 0.005,   # wash-detail
    7604654: 0.05,    # wash/check
    7604655: 0.020,   # full-history
    7604656: 0.010,   # transactions
    7604657: 0.005,   # buyers/profile
}

ATTRIBUTION_SOURCE_TAG = "x402watch_reconcile"

# Tolerance for amount comparison (5% of canonical price + tiny epsilon
# to absorb float rounding). Generous enough to handle on-chain
# settlement variance; tight enough to reject obviously-different prices.
_AMOUNT_TOLERANCE_PCT = 0.05


# ─── endpoint matching ────────────────────────────────────────────────
def _template_to_regex(template: str) -> re.Pattern:
    """`/api/v1/buyers/{address}/profile` → regex that matches
    `/api/v1/buyers/0x123ABC/profile`. Also handles `:name` colon-prefix
    style (DB convention) in case stats.jsonl ever emits that form."""
    pat = re.sub(r"\{[^/}]+\}", r"[^/]+", template)
    pat = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", r"[^/]+", pat)
    return re.compile("^" + pat + "$")


_ENDPOINT_REGEXES: list[tuple[re.Pattern, int, str]] = [
    (_template_to_regex(template), sid, template)
    for template, sid in ENDPOINT_TO_SERVICE_ID.items()
]


def lookup_service_id(endpoint: str) -> Optional[tuple[int, str]]:
    """Return (service_id, template) if endpoint matches one of the 5
    x402watch templates, else None. Templates are checked in dict
    insertion order; collisions between templates would be a design bug,
    but the 5 fixed templates don't overlap."""
    if not endpoint:
        return None
    # strip query string + trailing slash
    ep = endpoint.split("?", 1)[0].rstrip("/") or "/"
    for rx, sid, template in _ENDPOINT_REGEXES:
        if rx.match(ep):
            return sid, template
    return None


def amounts_match(stats_amount_usd: float, expected_price_usd: float,
                  tolerance_pct: float = _AMOUNT_TOLERANCE_PCT) -> bool:
    """5% of expected price + tiny epsilon (1e-6) to absorb rounding."""
    if expected_price_usd <= 0:
        return False
    diff = abs(stats_amount_usd - expected_price_usd)
    return diff <= max(expected_price_usd * tolerance_pct, 1e-6)


# ─── stats.jsonl reader ──────────────────────────────────────────────
def iter_payment_events(
    stats_path: Path, *, since: Optional[datetime] = None,
) -> Iterable[dict]:
    """Yield kind=payment events from stats.jsonl. Tolerates malformed
    lines (logs at DEBUG, skips). Applies the `since` filter via the
    event's `ts` field if present."""
    if not stats_path.exists():
        log.error("stats.jsonl not found: %s", stats_path)
        return
    with stats_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                log.debug("malformed jsonl line skipped")
                continue
            if d.get("kind") != "payment":
                continue
            if since is not None:
                ts_str = d.get("ts") or ""
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < since:
                        # caller still wants to see scanned=N including
                        # before-since events — we yield the row tagged
                        # so the reconcile loop can count it
                        d["_skip_before_since"] = True
                except Exception:
                    pass
            yield d


# ─── DB interface ────────────────────────────────────────────────────
class ReconcileDB:
    """Minimal interface the reconcile loop needs. Two impls below."""

    async def begin(self) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
    async def close(self) -> None: ...

    async def get_row_by_tx_hash(self, tx_hash: str) -> Optional[dict]:
        raise NotImplementedError

    async def update_attribution(
        self, tx_hash: str, service_id: int, attribution_source: str,
    ) -> None:
        raise NotImplementedError


class AsyncpgDB(ReconcileDB):
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.conn = None
        self._tx = None

    async def connect(self) -> None:
        import asyncpg  # lazy — self-test must work without asyncpg
        self.conn = await asyncpg.connect(self.dsn)

    async def begin(self) -> None:
        self._tx = self.conn.transaction()
        await self._tx.start()

    async def commit(self) -> None:
        if self._tx is not None:
            await self._tx.commit()
            self._tx = None

    async def rollback(self) -> None:
        if self._tx is not None:
            await self._tx.rollback()
            self._tx = None

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def get_row_by_tx_hash(self, tx_hash: str) -> Optional[dict]:
        row = await self.conn.fetchrow(
            "SELECT id, tx_hash, chain, service_id, attribution_source, "
            "is_x402_payment "
            "FROM transactions WHERE tx_hash = $1 LIMIT 1",
            tx_hash,
        )
        return dict(row) if row is not None else None

    async def update_attribution(
        self, tx_hash: str, service_id: int, attribution_source: str,
    ) -> None:
        await self.conn.execute(
            "UPDATE transactions "
            "   SET service_id        = $1, "
            "       attribution_source = $2, "
            "       is_x402_payment   = TRUE "
            " WHERE tx_hash = $3",
            service_id, attribution_source, tx_hash,
        )


class InMemoryDB(ReconcileDB):
    """In-memory stand-in for asyncpg, used by --self-test."""

    def __init__(self, rows: dict):
        self.rows: dict[str, dict] = {k: dict(v) for k, v in rows.items()}
        self._snapshot: Optional[dict] = None
        self.updates_log: list[tuple[str, int, str]] = []

    async def begin(self) -> None:
        self._snapshot = {k: dict(v) for k, v in self.rows.items()}

    async def commit(self) -> None:
        self._snapshot = None

    async def rollback(self) -> None:
        if self._snapshot is not None:
            self.rows = self._snapshot
            self._snapshot = None

    async def close(self) -> None:
        pass

    async def get_row_by_tx_hash(self, tx_hash: str) -> Optional[dict]:
        r = self.rows.get(tx_hash)
        return dict(r) if r is not None else None

    async def update_attribution(
        self, tx_hash: str, service_id: int, attribution_source: str,
    ) -> None:
        if tx_hash in self.rows:
            self.rows[tx_hash]["service_id"] = service_id
            self.rows[tx_hash]["attribution_source"] = attribution_source
            self.rows[tx_hash]["is_x402_payment"] = True
        self.updates_log.append((tx_hash, service_id, attribution_source))


# ─── counters ────────────────────────────────────────────────────────
@dataclass
class ReconcileCounts:
    scanned: int = 0
    skipped_no_tx_hash: int = 0
    skipped_before_since: int = 0
    skipped_unmapped_endpoint: int = 0
    skipped_amount_mismatch: int = 0
    already_correct: int = 0
    would_update: int = 0
    updated: int = 0
    not_found_in_db: int = 0
    update_by_template: dict[tuple[str, int], int] = field(default_factory=dict)


# ─── reconcile loop ──────────────────────────────────────────────────
async def reconcile(
    events: Iterable[dict], db: ReconcileDB, *, dry_run: bool,
) -> ReconcileCounts:
    """Iterate events, reconcile each. Wraps in a single transaction so
    dry-run = rollback at the end."""
    counts = ReconcileCounts()
    await db.begin()
    try:
        for ev in events:
            counts.scanned += 1

            if ev.get("_skip_before_since"):
                counts.skipped_before_since += 1
                continue

            tx_hash = ev.get("tx_hash")
            if not tx_hash:
                counts.skipped_no_tx_hash += 1
                continue

            endpoint = ev.get("endpoint") or ""
            match = lookup_service_id(endpoint)
            if match is None:
                counts.skipped_unmapped_endpoint += 1
                log.debug("unmapped endpoint skipped: %s tx=%s",
                          endpoint, tx_hash)
                continue
            correct_sid, template = match

            stats_amount = float(ev.get("amount_usd") or 0)
            expected = SERVICE_PRICE_USD[correct_sid]
            if not amounts_match(stats_amount, expected):
                counts.skipped_amount_mismatch += 1
                log.warning(
                    "amount mismatch: amount_usd=%s expected=$%.4f "
                    "endpoint=%s tx=%s — skipping",
                    stats_amount, expected, endpoint, tx_hash,
                )
                continue

            row = await db.get_row_by_tx_hash(tx_hash)
            if row is None:
                counts.not_found_in_db += 1
                log.debug("tx_hash not in transactions: %s endpoint=%s",
                          tx_hash, endpoint)
                continue

            current_sid = row.get("service_id")
            if current_sid == correct_sid:
                counts.already_correct += 1
                continue

            if dry_run:
                counts.would_update += 1
            else:
                await db.update_attribution(
                    tx_hash, correct_sid, ATTRIBUTION_SOURCE_TAG,
                )
                counts.updated += 1
                log.info(
                    "reconciled tx=%s: service_id %s → %s (endpoint=%s)",
                    tx_hash, current_sid, correct_sid, endpoint,
                )

            key = (template, correct_sid)
            counts.update_by_template[key] = (
                counts.update_by_template.get(key, 0) + 1
            )

        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception:
        await db.rollback()
        raise
    return counts


# ─── output formatting ───────────────────────────────────────────────
def format_summary(
    counts: ReconcileCounts, *, dry_run: bool,
    stats_path: Path, since: Optional[datetime],
) -> str:
    mode = "DRY RUN" if dry_run else "APPLY"
    verb_label = "would update" if dry_run else "updated"
    verb_count = counts.would_update if dry_run else counts.updated

    lines = [
        f"== reconcile x402watch attribution — {mode} ==",
        f"   stats.jsonl: {stats_path}",
        f"   since: {since.isoformat() if since else '(all)'}",
        "",
        f"scanned payment events:       {counts.scanned}",
        f"skipped (before --since):     {counts.skipped_before_since}",
        f"skipped (no tx_hash, pre-P3): {counts.skipped_no_tx_hash}",
        f"skipped (unmapped endpoint):  {counts.skipped_unmapped_endpoint}",
        f"skipped (amount mismatch):    {counts.skipped_amount_mismatch}",
        f"already correct service_id:   {counts.already_correct}",
        f"{verb_label:<30}{verb_count}",
        f"not found in transactions:    {counts.not_found_in_db}",
    ]
    if counts.update_by_template:
        lines.append("")
        lines.append(f"   {verb_label} breakdown:")
        for (template, sid), n in sorted(counts.update_by_template.items()):
            lines.append(f"     {template} → service_id {sid} ({n}건)")
    if dry_run and counts.would_update > 0:
        lines.append("")
        lines.append("DRY RUN OK — re-run with --apply to commit.")
    return "\n".join(lines)


# ─── self-test ───────────────────────────────────────────────────────
def _self_test_fixture():
    """7 synthetic stats.jsonl payment events covering every branch."""
    events = [
        # 1) buyers/profile, correct amount, wrong sid in DB → would update
        {"kind": "payment", "ts": "2026-05-29T20:00:00+09:00",
         "tx_hash": "0xAAA",
         "endpoint": "/api/v1/buyers/0x1234abcd/profile",
         "amount_usd": 0.005},
        # 2) wash/check, correct amount, wrong sid in DB → would update
        {"kind": "payment", "ts": "2026-05-29T20:01:00+09:00",
         "tx_hash": "0xBBB",
         "endpoint": "/api/v1/wash/check",
         "amount_usd": 0.05},
        # 3) wash-detail, correct sid already → already_correct
        {"kind": "payment", "ts": "2026-05-29T20:02:00+09:00",
         "tx_hash": "0xCCC",
         "endpoint": "/api/v1/services/833049/wash-detail",
         "amount_usd": 0.005},
        # 4) no tx_hash (pre-P3) → skipped_no_tx_hash
        {"kind": "payment", "ts": "2026-05-29T20:03:00+09:00",
         "tx_hash": None,
         "endpoint": "/api/v1/wash/check",
         "amount_usd": 0.05},
        # 5) unmapped endpoint → skipped_unmapped_endpoint
        {"kind": "payment", "ts": "2026-05-29T20:04:00+09:00",
         "tx_hash": "0xDDD",
         "endpoint": "/health",
         "amount_usd": 0.005},
        # 6) buyers/profile, correct amount, tx_hash NOT in DB → not_found
        {"kind": "payment", "ts": "2026-05-29T20:05:00+09:00",
         "tx_hash": "0xEEE",
         "endpoint": "/api/v1/buyers/0xqqq/profile",
         "amount_usd": 0.005},
        # 7) wash/check, BAD amount → skipped_amount_mismatch
        {"kind": "payment", "ts": "2026-05-29T20:06:00+09:00",
         "tx_hash": "0xFFF",
         "endpoint": "/api/v1/wash/check",
         "amount_usd": 99.99},
    ]
    db_rows = {
        # 1: currently absorbed into kr-sentiment (14741)
        "0xAAA": {"id": 1, "tx_hash": "0xAAA", "chain": "base",
                  "service_id": 14741, "attribution_source": None,
                  "is_x402_payment": False},
        # 2: currently absorbed into wash-detail (3268993)
        "0xBBB": {"id": 2, "tx_hash": "0xBBB", "chain": "base",
                  "service_id": 3268993, "attribution_source": None,
                  "is_x402_payment": False},
        # 3: already correct sid
        "0xCCC": {"id": 3, "tx_hash": "0xCCC", "chain": "base",
                  "service_id": 3268993, "attribution_source": None,
                  "is_x402_payment": False},
        # 7: row exists but won't reach DB step due to amount mismatch
        "0xFFF": {"id": 7, "tx_hash": "0xFFF", "chain": "base",
                  "service_id": 99, "attribution_source": None,
                  "is_x402_payment": False},
        # (0xDDD, 0xEEE intentionally absent)
    }
    expected = {
        "scanned": 7,
        "skipped_no_tx_hash": 1,
        "skipped_before_since": 0,
        "skipped_unmapped_endpoint": 1,
        "skipped_amount_mismatch": 1,
        "already_correct": 1,
        "would_update": 2,
        "not_found_in_db": 1,
    }
    return events, db_rows, expected


async def run_self_test() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="  %(levelname)s %(message)s")
    print("── endpoint-template matching ──")
    cases = [
        ("/api/v1/buyers/0x1234abcd/profile",        7604657),
        ("/api/v1/buyers/{address}/profile",         7604657),
        ("/api/v1/buyers/:address/profile",          7604657),
        ("/api/v1/wash/check",                       7604654),
        ("/api/v1/wash/check?foo=1",                 7604654),
        ("/api/v1/wash/check/",                      7604654),
        ("/api/v1/services/833049/wash-detail",      3268993),
        ("/api/v1/services/833049/transactions",     7604656),
        ("/api/v1/categories/defi/full-history",     7604655),
        ("/health",                                  None),
        ("/api/v1/services/833049/something-else",   None),
        ("",                                         None),
    ]
    match_ok = True
    for ep, expect_sid in cases:
        got = lookup_service_id(ep)
        got_sid = got[0] if got else None
        ok = got_sid == expect_sid
        if not ok:
            match_ok = False
        print(("  OK   " if ok else "  FAIL ")
              + f"endpoint={ep!r:<55} sid={got_sid} (expect {expect_sid})")
    if not match_ok:
        return 2

    print()
    print("── amount-tolerance check ──")
    amount_cases = [
        (0.005,  0.005, True),    # exact
        (0.005,  0.0049, True),   # within 5%
        (0.005,  0.0051, True),
        (0.005,  0.01, False),    # 2x off
        (99.99,  0.05, False),    # mismatch
        (0.0,    0.005, False),
    ]
    for stats_a, expected, want in amount_cases:
        got = amounts_match(stats_a, expected)
        ok = got == want
        if not ok:
            match_ok = False
        print(("  OK   " if ok else "  FAIL ")
              + f"amounts_match(stats={stats_a}, expected={expected}) = "
              + f"{got} (want {want})")
    if not match_ok:
        return 2

    print()
    print("── reconcile loop: dry-run against in-memory DB ──")
    events, db_rows, expected_counts = _self_test_fixture()
    db = InMemoryDB(db_rows)
    counts = await reconcile(events, db, dry_run=True)
    print(format_summary(counts, dry_run=True,
                         stats_path=Path("<fixture>"), since=None))

    ok = True
    for k, v in expected_counts.items():
        actual = getattr(counts, k)
        if actual != v:
            ok = False
            print(f"  FAIL  {k}: actual={actual} expected={v}")
    if not ok:
        return 2
    # dry-run must not have mutated rows
    if db.rows["0xAAA"]["service_id"] != 14741:
        print("  FAIL  dry-run mutated 0xAAA row")
        return 2
    print("  OK   counts match + dry-run did not mutate")

    print()
    print("── reconcile loop: apply against in-memory DB ──")
    db2 = InMemoryDB(db_rows)
    counts2 = await reconcile(events, db2, dry_run=False)
    print(format_summary(counts2, dry_run=False,
                         stats_path=Path("<fixture>"), since=None))

    if counts2.updated != 2:
        print(f"  FAIL  updated={counts2.updated} expected 2")
        return 2
    if db2.rows["0xAAA"]["service_id"] != 7604657:
        print("  FAIL  0xAAA not re-attributed to 7604657")
        return 2
    if db2.rows["0xAAA"]["attribution_source"] != ATTRIBUTION_SOURCE_TAG:
        print("  FAIL  0xAAA attribution_source not tagged")
        return 2
    if db2.rows["0xAAA"]["is_x402_payment"] is not True:
        print("  FAIL  0xAAA is_x402_payment not set TRUE")
        return 2
    if db2.rows["0xBBB"]["service_id"] != 7604654:
        print("  FAIL  0xBBB not re-attributed to 7604654")
        return 2
    if db2.rows["0xCCC"]["service_id"] != 3268993:
        print("  FAIL  0xCCC mutated despite being already correct")
        return 2
    if db2.rows["0xCCC"]["attribution_source"] is not None:
        print("  FAIL  0xCCC attribution_source touched")
        return 2
    print("  OK   apply mutations correct + already-correct rows untouched")

    print()
    print("── reconcile loop: idempotency (re-apply on result of apply) ──")
    db3 = InMemoryDB(db2.rows)
    counts3 = await reconcile(events, db3, dry_run=False)
    if counts3.updated != 0:
        print(f"  FAIL  re-run updated={counts3.updated} expected 0")
        return 2
    if counts3.already_correct != 3:
        print(f"  FAIL  re-run already_correct={counts3.already_correct} "
              "expected 3")
        return 2
    print(f"  OK   idempotent (updated=0, already_correct=3)")

    print()
    print("✓ all self-test cases passed")
    return 0


# ─── main ────────────────────────────────────────────────────────────
async def main_async() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="commit changes (default: dry-run + rollback)")
    ap.add_argument("--stats-jsonl",
                    default="/home/ubuntu/x402watch/var/stats.jsonl")
    ap.add_argument("--since", default=None,
                    help="ISO timestamp; only events with ts >= since are "
                         "reconciled. Recommended: P3 fix time "
                         "(2026-05-29T19:56:00+09:00)")
    ap.add_argument("--dsn", default=os.environ.get("X402WATCH_DSN") or "",
                    help="postgres DSN; falls back to $X402WATCH_DSN")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return await run_self_test()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    stats_path = Path(args.stats_jsonl)
    if not stats_path.exists():
        log.error("stats.jsonl not found: %s", stats_path)
        return 2

    since = None
    if args.since:
        since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

    if not args.dsn:
        log.error(
            "no DSN — set $X402WATCH_DSN or pass --dsn 'postgresql://...'"
        )
        return 2

    db = AsyncpgDB(args.dsn)
    await db.connect()
    try:
        events = iter_payment_events(stats_path, since=since)
        counts = await reconcile(events, db, dry_run=not args.apply)
    finally:
        await db.close()

    print(format_summary(counts, dry_run=not args.apply,
                         stats_path=stats_path, since=since))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
