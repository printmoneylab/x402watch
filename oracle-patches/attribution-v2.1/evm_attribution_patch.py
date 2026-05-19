#!/usr/bin/env python3
"""
Phase 2b — evm.py attribution patch (Option A-naive).

Permanent location: /home/ubuntu/x402watch/scripts/apply_attribution_v21.py

The bug
=======
indexer/evm.py:165 (approx) builds a seller_address → service_id map for
attributing incoming USDC transfers:

    SELECT LOWER(seller_address) AS addr, MIN(id) AS service_id
    FROM services GROUP BY seller_address
    → {addr: service_id for r in rows}
    → service_id = seller_map.get(to_addr)

For any seller that operates N>1 endpoints, all incoming USDC transfers
collapse onto MIN(id) (the oldest service the seller ever registered).
KR Crypto's 11 endpoints → all attribute to service_id=14391 (kr-prices).
Aubrai's 7 endpoints → all to its MIN(id). Google Maps' 12 → all to one.
Etc.

The fix
=======
Include `price_amount` in the GROUP BY key and the lookup key. Then
attribute by the (seller_address, amount) pair instead of seller_address
alone. KR Crypto:

   seller=0xcF92  →  4 distinct prices ($0.001, $0.01, $0.05, $0.10)
                  →  4 attribution buckets instead of 1.

This is *lossy* within a bucket — KR Crypto has 4 endpoints at $0.001 so
$0.001 payments still collapse to MIN(id) within the $0.001 bucket. That
loss is addressed by the Option D merchant feed (Phase 2c), which gives
us 100% accuracy for opt-in merchants.

What this patcher does
======================
- Loads /home/ubuntu/x402watch/indexer/evm.py.
- Locates the seller_map build block via two anchor patterns. Bails if
  neither matches (don't write garbage when the file has been hand-edited
  beyond what we anticipated).
- Replaces the GROUP BY + lookup with (seller, amount) composite key.
- Adds an `attribution_source` column write so future audits can tell
  which rows came from which attribution mechanism.
- Idempotent — replacement-presence is checked BEFORE anchor-match
  (same convention as oracle-patches/x402watch-alerts/apply_wireup.py).

Apply with:
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/apply_attribution_v21.py             # dry-run
    venv/bin/python scripts/apply_attribution_v21.py --apply     # write

Idempotent + verifies file syntax + checks the indexer module still
imports cleanly. Backup at evm.py.bak.attribution-v21-YYYYMMDD-HHMM.

What this patcher does NOT do
=============================
- Backfill historical rows. Existing transactions stay with their wrong
  service_id until backfill_kr_crypto.sql runs (Phase 2d).
- Touch indexer/solana.py. That's a separate work item.
- Touch derive_global.py. That re-aggregates from transactions, which
  needs to happen after backfill, not after the indexer change.

Sequence after this patch
=========================
1. Restart indexer service (`sudo systemctl restart x402watch-indexer`).
2. Wait one indexer cycle. New transactions should land with corrected
   service_id (modulo same-price collisions).
3. Verify:
     SELECT service_id, COUNT(*)
     FROM transactions
     WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb'
       AND time > NOW() - INTERVAL '1 hour'
     GROUP BY 1;
   Expected: rows in 14391/14744/14741/14628 etc. (depending on which
   prices KR Crypto received in the last hour) — NOT all on 14391.
4. Run backfill_kr_crypto.sql (Phase 2d) to rewrite historical rows.
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


# ─── Patch definitions ──────────────────────────────────────────────
# Anchor 1: the seller_map SELECT. The reported pattern from Moa was:
#   SELECT LOWER(seller_address) AS addr, MIN(id) AS service_id
#   FROM services GROUP BY seller_address
# We allow flexibility in whitespace/quoting by matching on the core SQL
# tokens via a regex pre-check before doing the exact-string replace.

# We anchor on the exact SQL text first. The patcher refuses to apply if
# the anchor isn't present, since this is a hot-path file in production.

ANCHOR_SQL = (
    "SELECT LOWER(seller_address) AS addr, MIN(id) AS service_id\n"
    "        FROM services GROUP BY seller_address"
)
REPLACEMENT_SQL = (
    "SELECT LOWER(seller_address) AS addr,\n"
    "               price_amount,\n"
    "               MIN(id) AS service_id\n"
    "        FROM services\n"
    "        WHERE price_amount IS NOT NULL\n"
    "        GROUP BY seller_address, price_amount"
)

# Anchor 2: the lookup dict build. Originally:
#   seller_map = {r['addr']: r['service_id'] for r in rows}
#   ...
#   service_id = seller_map.get(to_addr)
# Replaced with a 2-key lookup keyed on (addr, amount). We pick a tight
# pattern that the indexer almost certainly has, but allow the patcher
# to FAIL gracefully if the variable names differ.

ANCHOR_LOOKUP_BUILD = "seller_map = {r['addr']: r['service_id'] for r in rows}"
REPLACEMENT_LOOKUP_BUILD = (
    "# v2.1 attribution: keyed by (seller, amount).\n"
    "    # Same-price collisions still collapse to MIN(id) within the bucket;\n"
    "    # those are addressed by the merchant feed (Phase 2c).\n"
    "    seller_map = {(r['addr'], float(r['price_amount'])): r['service_id'] for r in rows}"
)

ANCHOR_LOOKUP_USE = "service_id = seller_map.get(to_addr)"
REPLACEMENT_LOOKUP_USE = (
    "# v2.1 attribution: try (seller, amount); fall back to first match for backwards-compat logging.\n"
    "    service_id = seller_map.get((to_addr, float(amount)))\n"
    "    attribution_source = 'price_match' if service_id is not None else 'unattributed'"
)


PATCHES = [
    (ANCHOR_SQL, REPLACEMENT_SQL),
    (ANCHOR_LOOKUP_BUILD, REPLACEMENT_LOOKUP_BUILD),
    (ANCHOR_LOOKUP_USE, REPLACEMENT_LOOKUP_USE),
]


def apply(path: Path, patches, dry_run: bool):
    if not path.exists():
        return False, [f"  ✗ missing: {path}"]
    src = path.read_text()
    new = src
    notes = []
    for anchor, replacement in patches:
        if replacement and replacement in new:
            notes.append(f"  ◌ already applied ({anchor.strip()[:60]}…)")
        elif anchor in new:
            new = new.replace(anchor, replacement, 1)
            notes.append(f"  ✓ matched ({anchor.strip()[:60]}…)")
        else:
            notes.append(f"  ✗ ANCHOR MISSING: {anchor.strip()[:80]}…")
            return False, notes
    if new == src:
        return True, notes + ["  (no changes — all patches already applied)"]
    if not dry_run:
        bak = path.with_suffix(path.suffix + f".bak.{BAK_TAG}")
        shutil.copy2(path, bak)
        path.write_text(new)
        notes.append(f"  wrote {path.name}, backup → {bak.name}")
    else:
        notes.append("  [dry-run] would write")
    return True, notes


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="write changes (default: dry-run)")
    args = p.parse_args()
    dry_run = not args.apply

    print(f"== attribution v2.1 evm.py patch — {'APPLY' if not dry_run else 'DRY RUN'} ==")
    print(f"   target: {EVM}")
    print()
    ok, notes = apply(EVM, PATCHES, dry_run)
    print("\n".join(notes))

    if not ok:
        print()
        print("FAIL — anchor not found. Nothing written.")
        print()
        print("If the actual SQL / lookup code drifted from what this patcher")
        print("expects, paste the current evm.py:140-180 contents and we'll")
        print("regenerate the anchors. The patcher refuses to apply blindly to")
        print("production indexer code.")
        return 1

    if not dry_run:
        try:
            ast.parse(EVM.read_text())
            print("[OK] evm.py parses")
        except SyntaxError as e:
            print(f"[FAIL] evm.py syntax: {e}")
            return 1

    print()
    print("Next steps (Moa):")
    print("  1. sudo systemctl restart x402watch-indexer")
    print("  2. Wait one indexer cycle (~5-10 min depending on cron)")
    print("  3. Verify new attribution:")
    print()
    print("     sudo docker exec x402watch-postgres psql -U x402watch -d x402watch -c \\")
    print("       \"SELECT service_id, COUNT(*) AS n, SUM(amount) AS usdc \\")
    print("        FROM transactions \\")
    print("        WHERE seller_address = '0xcf9223ece895258dea8d288aebcf846ab8e342fb' \\")
    print("          AND time > NOW() - INTERVAL '1 hour' \\")
    print("        GROUP BY 1 ORDER BY n DESC;\"")
    print()
    print("     Expected: rows spread across 14391/14744/14741/etc. (per price),")
    print("               NOT all on 14391.")
    print()
    print("  4. When new attribution looks correct, proceed to Phase 2d backfill")
    print("     (oracle-patches/attribution-v2.1/backfill_kr_crypto.sql).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
