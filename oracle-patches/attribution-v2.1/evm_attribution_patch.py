#!/usr/bin/env python3
"""
Phase 2b — evm.py attribution patch (Option A: seller+amount keying).

Permanent location: /home/ubuntu/x402watch/scripts/apply_attribution_v21.py

v2 of this patcher — rewritten against the ACTUAL evm.py source Moa
pasted (the first draft assumed `GROUP BY seller_address` with no
WHERE/LOWER; the real code has `WHERE chain = $1` and
`GROUP BY LOWER(seller_address)`).

The bug
=======
indexer/evm.py `load_seller_map()` builds a per-chain
seller_address → service_id map and `parse_log()` looks payments up by
recipient address alone:

    async def load_seller_map(conn, chain):
        rows = await conn.fetch('''
            SELECT LOWER(seller_address) AS addr, MIN(id) AS service_id
            FROM services WHERE chain = $1 GROUP BY LOWER(seller_address)
        ''', chain)
        return {r['addr']: r['service_id'] for r in rows}

One seller wallet → one service_id (the oldest, via MIN(id)). Every
multi-endpoint operator collapses. KR Crypto's 11 endpoints all →
service_id 14391.

The fix
=======
Key the map by (lower(seller_address), amount_micro) where
amount_micro = ROUND(price_amount * 1e6) — the integer micro-USDC
value, which equals the raw `value` field of a USDC Transfer log
(USDC = 6 decimals on Base and Solana). A service with NULL
price_amount is keyed (addr, None) and acts as the fallback when an
exact (addr, amount) match is absent.

This is the *partial* fix. Same-price collisions inside one seller
(KR Crypto has 4 endpoints at $0.001) still resolve to MIN(id) within
the bucket. The merchant feed (Phase 2c) removes that residual loss.

THREE patches, all required
===========================
  P1  load_seller_map()  — full-function replacement (exact source).
  P2  parse_log() signature — `seller_map` type annotation.
  P3  parse_log() body lookup — `seller_map.get(<addr>)` →
      `seller_map.get((<addr>, amount)) or seller_map.get((<addr>, None))`.

P1 + P2 anchors are EXACT (built from Moa's paste). P3 is a best
guess: it assumes the lookup is literally `seller_map.get(to_addr)`
and that a raw-integer micro-USDC `amount` variable is in scope at
that point. If the real parse_log uses a different variable name or
a dollar-float amount, P3's anchor will not match and the patcher
BAILS WITHOUT WRITING ANYTHING, then prints every `seller_map` /
amount-looking line so the anchor can be finalised.

The patcher is all-or-nothing: it never applies P1+P2 without P3,
because a tuple-keyed map with a scalar lookup would null every
attribution.

Apply with:
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/apply_attribution_v21.py             # dry-run
    venv/bin/python scripts/apply_attribution_v21.py --apply     # write

Idempotent (replacement-presence checked before anchor-match).
Backup at evm.py.bak.attribution-v21-YYYYMMDD-HHMM.
"""
from __future__ import annotations

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/ubuntu/x402watch")
EVM = ROOT / "indexer" / "evm.py"
KST = timezone(timedelta(hours=9))
BAK_TAG = "attribution-v21-" + datetime.now(KST).strftime("%Y%m%d-%H%M")


# ─── P1: load_seller_map full-function replacement ──────────────────
# Anchor is the EXACT source Moa pasted (evm.py:162-172).
P1_ANCHOR = '''async def load_seller_map(conn, chain: str) -> dict[str, int]:
    rows = await conn.fetch(
        """
        SELECT LOWER(seller_address) AS addr, MIN(id) AS service_id
        FROM services
        WHERE chain = $1
        GROUP BY LOWER(seller_address)
        """,
        chain,
    )
    return {r["addr"]: r["service_id"] for r in rows}'''

P1_REPLACEMENT = '''async def load_seller_map(conn, chain: str) -> dict[tuple[str, int | None], int]:
    # v2.1 attribution — keyed by (lower(seller_address), amount_micro).
    # amount_micro = ROUND(price_amount * 1e6) matches the raw integer
    # `value` of a USDC Transfer log (USDC = 6 decimals on Base + Solana).
    # A service with NULL price_amount is keyed (addr, None) and serves
    # as the fallback when an exact (addr, amount) match is absent.
    # Same-price collisions within one seller still collapse to MIN(id);
    # the merchant feed (Phase 2c) removes that residual loss.
    rows = await conn.fetch(
        """
        SELECT LOWER(seller_address) AS addr,
               CASE WHEN price_amount IS NULL THEN NULL
                    ELSE ROUND(price_amount * 1000000)::bigint
               END AS amount_micro,
               MIN(id) AS service_id
        FROM services
        WHERE chain = $1
        GROUP BY LOWER(seller_address), amount_micro
        """,
        chain,
    )
    return {(r["addr"], r["amount_micro"]): r["service_id"] for r in rows}'''


# ─── P2: parse_log signature type annotation ────────────────────────
P2_ANCHOR = "    seller_map: dict[str, int],\n"
P2_REPLACEMENT = "    seller_map: dict[tuple[str, int | None], int],\n"


# ─── P3: parse_log body lookup (BEST GUESS) ─────────────────────────
# Assumption: the lookup is literally `seller_map.get(to_addr)` and a
# raw-integer micro-USDC `amount` variable is in scope. If wrong, the
# patcher bails (see scan_seller_map_usage()).
P3_ANCHOR = "seller_map.get(to_addr)"
P3_REPLACEMENT = (
    "seller_map.get((to_addr, amount)) or seller_map.get((to_addr, None))"
)


PATCHES = [
    ("P1 load_seller_map", P1_ANCHOR, P1_REPLACEMENT),
    ("P2 parse_log signature", P2_ANCHOR, P2_REPLACEMENT),
    ("P3 parse_log lookup", P3_ANCHOR, P3_REPLACEMENT),
]


def scan_seller_map_usage(src: str) -> list[str]:
    """Return every line that mentions seller_map or looks like it
    extracts a transfer amount — diagnostic output when P3 misses."""
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        low = line.lower()
        if "seller_map" in low:
            out.append(f"  L{i}: {line.rstrip()}")
        elif re.search(r"\bamount\b|\bvalue\b|int\(lg\[|topics\[", low):
            out.append(f"  L{i}: {line.rstrip()}")
    return out


def apply(path: Path, dry_run: bool):
    if not path.exists():
        return False, [f"  ✗ missing: {path}"], None
    src = path.read_text()
    new = src
    notes = []
    all_ok = True
    for name, anchor, replacement in PATCHES:
        if replacement in new:
            notes.append(f"  ◌ {name}: already applied")
        elif anchor in new:
            new = new.replace(anchor, replacement, 1)
            notes.append(f"  ✓ {name}: matched")
        else:
            notes.append(f"  ✗ {name}: ANCHOR MISSING")
            all_ok = False
    if not all_ok:
        return False, notes, src
    if new == src:
        return True, notes + ["  (no changes — all patches already applied)"], src
    if not dry_run:
        bak = path.with_suffix(path.suffix + f".bak.{BAK_TAG}")
        shutil.copy2(path, bak)
        path.write_text(new)
        notes.append(f"  wrote {path.name}, backup → {bak.name}")
    else:
        notes.append("  [dry-run] would write")
    return True, notes, new


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="write changes (default: dry-run)")
    args = p.parse_args()
    dry_run = not args.apply

    print(f"== attribution v2.1 evm.py patch — {'APPLY' if not dry_run else 'DRY RUN'} ==")
    print(f"   target: {EVM}")
    print()
    ok, notes, src = apply(EVM, dry_run)
    print("\n".join(notes))

    if not ok:
        print()
        print("FAIL — at least one anchor missing. Nothing written.")
        print()
        if src is not None:
            print("seller_map / amount usage in evm.py (paste this back to finalise P3):")
            for line in scan_seller_map_usage(src):
                print(line)
        print()
        print("If P3 missed: the real parse_log lookup is NOT")
        print("`seller_map.get(to_addr)`. Send the parse_log body so the")
        print("P3 anchor + the amount-variable name can be set exactly.")
        return 1

    if not dry_run:
        try:
            ast.parse(EVM.read_text())
            print("[OK] evm.py parses")
        except SyntaxError as e:
            print(f"[FAIL] evm.py syntax: {e}")
            return 1

    print()
    print("Next (Moa):")
    print("  1. sudo systemctl restart x402watch-indexer")
    print("  2. wait one indexer cycle")
    print("  3. verify new attribution spreads across price tiers:")
    print("     SELECT service_id, COUNT(*) FROM transactions")
    print("     WHERE seller_address='0xcf9223ece895258dea8d288aebcf846ab8e342fb'")
    print("       AND time > NOW() - INTERVAL '1 hour' GROUP BY 1;")
    print("  4. then Phase 2d backfill (backfill_kr_crypto.sql)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
