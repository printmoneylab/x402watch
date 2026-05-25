#!/usr/bin/env python3
"""
Tier 2/3 → daily transition (2-b) — silence real-time AI-client /
agent-framework MCP alerts; keep them in the daily KST 09:00 digest.

What this changes
=================
`app/client_classifier.py` only — flips two `action="immediate"` literals
inside the Tier 2 and Tier 3 return statements to `action="daily"`.

Effect chain:
  classifier.action == "daily"
    → telegram_notify.notify_mcp_tool() early-returns (line ~214)
    → no Telegram alert
  daily_summary.rollup() re-classifies every mcp_call via classify(ua)
    → c.tier still 2/3
    → tier_counter[2] / tier_counter[3] still incremented
    → "tier breakdown" lines still appear in the 09:00 digest
  stats.jsonl mcp_call logging in mcp_server._track() unchanged
    → raw events still on disk for daily / post-hoc analysis.

Preserved verbatim
==================
- Tier 1 (paid x402)      → action="immediate"  (real-time)
- Tier 6 (suspect)        → action="immediate"  (promote_to_suspect)
- Tier 0 (unknown UA)     → action="first_only" (24h per-UA dedupe)
- payment alerts          (notify_payment — no action gate)
- daily_summary aggregation (this is the whole point)
- mcp_server._track() stats.jsonl emission

Usage
=====
  dry-run :  venv/bin/python scripts/tier23_to_daily.py
  apply   :  venv/bin/python scripts/tier23_to_daily.py --apply

Idempotent — checks for the post-patch fingerprint before touching
the anchor; re-running prints "already patched" and exits 0.
AST-parse gate; KST-tagged backup auto-written next to the file.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/x402watch")
TARGET = ROOT / "app" / "client_classifier.py"

# ── Anchors (verbatim from client_classifier.py lines 151-158) ───────
# Two-line returns. Whitespace MUST match the file exactly. The
# `tier=N, label=label, emoji=…` prefix on the second-line continuation
# starts at column 35 (12 leading spaces for the `return`, "return " +
# "Classification(" = 22 chars). The wrap aligns `action=` under `tier=`.
TIER2_ANCHOR = (
    '            return Classification(tier=2, label=label, emoji="🔵",\n'
    '                                  action="immediate", pattern=rx.pattern)'
)
TIER2_REPLACEMENT = (
    '            return Classification(tier=2, label=label, emoji="🔵",\n'
    '                                  action="daily", pattern=rx.pattern)'
)

TIER3_ANCHOR = (
    '            return Classification(tier=3, label=label, emoji="🟡",\n'
    '                                  action="immediate", pattern=rx.pattern)'
)
TIER3_REPLACEMENT = (
    '            return Classification(tier=3, label=label, emoji="🟡",\n'
    '                                  action="daily", pattern=rx.pattern)'
)

# Post-patch fingerprints — exact substrings the patched file must
# contain. Used for the "already patched" short-circuit.
TIER2_FINGERPRINT = TIER2_REPLACEMENT
TIER3_FINGERPRINT = TIER3_REPLACEMENT

# Pre-patch fingerprints — exact substrings the unpatched file must
# contain. Used to refuse mid-state files (one tier patched, one not).
TIER2_PRE_FINGERPRINT = TIER2_ANCHOR
TIER3_PRE_FINGERPRINT = TIER3_ANCHOR


def _kst_tag() -> str:
    # KST stamp for the backup filename. Pure datetime — no zoneinfo
    # dep so this runs on a slim venv.
    now_utc = dt.datetime.utcnow()
    kst = now_utc + dt.timedelta(hours=9)
    return kst.strftime("%Y%m%d-%H%M")


def _die(msg: str, code: int = 2) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(code)


def _patch(text: str) -> tuple[str, list[str]]:
    """Return (new_text, notes). Raises on anchor drift / mid-state."""
    notes: list[str] = []

    has_t2_old = TIER2_PRE_FINGERPRINT in text
    has_t2_new = TIER2_FINGERPRINT in text
    has_t3_old = TIER3_PRE_FINGERPRINT in text
    has_t3_new = TIER3_FINGERPRINT in text

    # All four states are possible. Resolve them.
    if has_t2_new and has_t3_new and not has_t2_old and not has_t3_old:
        notes.append("◌ already patched (Tier 2 + Tier 3 both daily) — no-op")
        return text, notes

    if has_t2_new ^ has_t3_new:
        # One side already patched, the other not — refuse rather than
        # leave a mid-state file.
        _die(
            "mid-state: only one of Tier 2 / Tier 3 is already daily. "
            "Inspect manually or restore from backup before re-running."
        )

    if not has_t2_old:
        _die("Tier 2 anchor not found — client_classifier.py drifted")
    if not has_t3_old:
        _die("Tier 3 anchor not found — client_classifier.py drifted")

    # Both anchors present in their old form. Apply.
    new = text.replace(TIER2_ANCHOR, TIER2_REPLACEMENT, 1)
    new = new.replace(TIER3_ANCHOR, TIER3_REPLACEMENT, 1)

    # Sanity: replacement count should be exactly one each.
    if new.count(TIER2_REPLACEMENT) != 1:
        _die("Tier 2 replacement count != 1 (file structure unexpected)")
    if new.count(TIER3_REPLACEMENT) != 1:
        _die("Tier 3 replacement count != 1 (file structure unexpected)")
    # And neither old form should remain.
    if TIER2_PRE_FINGERPRINT in new:
        _die("Tier 2 old form still present after replace (bug)")
    if TIER3_PRE_FINGERPRINT in new:
        _die("Tier 3 old form still present after replace (bug)")

    notes.append('✓ Tier 2 action: "immediate" → "daily"')
    notes.append('✓ Tier 3 action: "immediate" → "daily"')
    return new, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the patch (default is dry-run)")
    ap.add_argument("--target", default=str(TARGET),
                    help=f"override target path (default {TARGET})")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        _die(f"target not found: {target}")
    src = target.read_text(encoding="utf-8")

    try:
        new, notes = _patch(src)
    except SystemExit:
        raise

    for n in notes:
        print(n)

    if new == src:
        # Either already patched (note already printed) or nothing to do.
        return 0

    # AST-parse gate on the proposed output before we commit it.
    try:
        ast.parse(new)
    except SyntaxError as e:
        _die(f"ast.parse failed on patched output: {e}")
    print("✓ ast.parse OK")

    if not args.apply:
        print("(dry-run — re-run with --apply to write)")
        return 0

    backup = target.with_suffix(target.suffix + f".bak.tier23-daily-{_kst_tag()}")
    shutil.copy2(target, backup)
    print(f"✓ backup: {backup.name}")
    target.write_text(new, encoding="utf-8")
    print(f"✓ wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
