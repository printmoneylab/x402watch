#!/usr/bin/env python3
"""
Remove the legacy MCP alert path (path B) from mcp_server.py `_track()`.

Permanent location: /home/ubuntu/x402watch/scripts/remove_legacy_mcp_alert_path.py

The bug
=======
`_track()` (built by apply_wireup.py, then revised by apply_mcp_ctx.py)
fires Telegram on TWO paths per MCP tool call:

  Path A — tier-aware, KEEP:
      asyncio.create_task(_notify_mcp_tool(
          tool_name=tool_name, classification=_classify(ua),
          ip=ip, user_agent=ua, is_paid_tool=False,
      ))
    Tier 0 (empty UA) → dedupe key `unknown:{ua}` → 1 alert / 24h.
    Tier 4/5 → suppressed. Tier 1/2/3/6 → 5-min dedupe. Correct.

  Path B — legacy, REMOVE:
      # Existing cooldown-gated alert preserved verbatim.
      now = time.monotonic()
      if now - _last_notified.get(tool_name, 0) < _NOTIFY_COOLDOWN_SECONDS:
          return
      _last_notified[tool_name] = now
      asyncio.create_task(_tg_notify(f"x402watch MCP: {tool_name}"))
    Tier-blind + IP-blind, 5-min-per-tool cooldown only. On 2026-05-21 a
    single Tier-0 burst (which path A would have deduped to ONE alert)
    produced 200+ Telegram messages via path B: 5 tools × ~12 five-minute
    rounds over a 7h window, multiplied by IP variety.

apply_mcp_ctx.py's own comment calls path B "Existing cooldown-gated
alert preserved verbatim" — it is a pre-tier-system leftover that
should have been folded into path A.

What this patcher does
======================
1. Removes the 6-line path-B block from `_track()`. The block text is
   IDENTICAL whether the file is at the apply_wireup.py stage or the
   apply_mcp_ctx.py stage (only path A's args differ between them), so a
   single anchor matches both.
2. Self-checks whether `_last_notified` / `_NOTIFY_COOLDOWN_SECONDS` /
   `time.` are still referenced anywhere AFTER the removal. If a symbol
   is now unused, its module-level definition (or `import time`) is
   removed too. If still used, it is kept and a note is printed.
3. `_tg_notify` itself is NEVER touched — it stays defined + imported
   (payment alerts and other call sites may use it).
4. ast.parse() validates the result before writing.

Idempotent: a second run finds no path-B block and prints
"already patched".

Usage:
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/remove_legacy_mcp_alert_path.py            # dry-run
    venv/bin/python scripts/remove_legacy_mcp_alert_path.py --apply    # write

Backup: app/mcp_server.py.bak.dedupe-fix-YYYYMMDD-HHMM (KST).
Only mcp_server.py is touched.
"""
from __future__ import annotations

import argparse
import ast
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

MCP = Path("/home/ubuntu/x402watch/app/mcp_server.py")
KST = timezone(timedelta(hours=9))
BAK_TAG = "dedupe-fix-" + datetime.now(KST).strftime("%Y%m%d-%H%M")

# Path B — the exact 6-line block, identical at both wireup stages.
PATH_B = (
    "    # Existing cooldown-gated alert preserved verbatim.\n"
    "    now = time.monotonic()\n"
    "    if now - _last_notified.get(tool_name, 0) < _NOTIFY_COOLDOWN_SECONDS:\n"
    "        return\n"
    "    _last_notified[tool_name] = now\n"
    "    asyncio.create_task(_tg_notify(f\"x402watch MCP: {tool_name}\"))\n"
)

# Sentinel that proves a path-B-shaped alert exists even if the block
# text drifted — used to tell "already patched" from "anchor missing".
PATH_B_SENTINEL = '_tg_notify(f"x402watch MCP: {tool_name}")'


def main() -> int:
    p = argparse.ArgumentParser(
        description="Remove legacy MCP alert path B from mcp_server.py _track()")
    p.add_argument("--apply", action="store_true",
                   help="write changes (default: dry-run)")
    args = p.parse_args()
    dry_run = not args.apply

    print(f"== remove legacy MCP alert path B — {'APPLY' if not dry_run else 'DRY RUN'} ==")
    print(f"   target: {MCP}")
    print()

    if not MCP.exists():
        print(f"FAIL — {MCP} not found")
        return 1
    src = MCP.read_text()
    notes: list[str] = []

    # ── Step 1: locate + remove path B ──────────────────────────────
    if PATH_B not in src:
        if PATH_B_SENTINEL in src:
            print("✗ ANCHOR MISSING — a path-B-shaped `_tg_notify(\"x402watch "
                  "MCP: …\")` call exists but the surrounding 6-line block "
                  "does not match the expected text.")
            print()
            print("  Lines mentioning _tg_notify / _last_notified in mcp_server.py:")
            for i, line in enumerate(src.splitlines(), 1):
                if "_tg_notify" in line or "_last_notified" in line:
                    print(f"    L{i}: {line.rstrip()}")
            print()
            print("  Paste these so the anchor can be re-derived. Nothing written.")
            return 1
        print("◌ already patched — no path-B block in _track(). Nothing to do.")
        return 0

    new = src.replace(PATH_B, "", 1)
    notes.append("✓ path B removed from _track()")

    # ── Step 2: prune now-unused symbols (self-checked) ─────────────
    # _last_notified — its module-level def is `_last_notified...= {}`.
    # If after the removal the name appears only once (that def), drop it.
    if new.count("_last_notified") == 1:
        new2 = re.sub(r"^_last_notified\b.*\n", "", new, count=1, flags=re.M)
        if new2 != new:
            new = new2
            notes.append("✓ removed now-unused `_last_notified` definition")
    elif "_last_notified" in new:
        notes.append("◌ `_last_notified` still referenced elsewhere — definition kept")

    if new.count("_NOTIFY_COOLDOWN_SECONDS") == 1:
        new2 = re.sub(r"^_NOTIFY_COOLDOWN_SECONDS\b.*\n", "", new, count=1, flags=re.M)
        if new2 != new:
            new = new2
            notes.append("✓ removed now-unused `_NOTIFY_COOLDOWN_SECONDS` definition")
    elif "_NOTIFY_COOLDOWN_SECONDS" in new:
        notes.append("◌ `_NOTIFY_COOLDOWN_SECONDS` still referenced — definition kept")

    # time — drop `import time` only if no `time.` usage remains.
    if not re.search(r"\btime\.", new):
        new2 = re.sub(r"^import time\n", "", new, count=1, flags=re.M)
        if new2 != new:
            new = new2
            notes.append("✓ removed now-unused `import time`")
    else:
        notes.append("◌ `time.` still used elsewhere — `import time` kept")

    # ── Step 3: safety — _tg_notify must still be defined + imported ─
    if "_tg_notify" not in new:
        print("✗ ABORT — `_tg_notify` vanished from the file. The patcher only "
              "removes path B's CALL, never the function. Nothing written.")
        return 1
    notes.append("✓ `_tg_notify` definition/import preserved")

    # ── Step 4: ast validation ──────────────────────────────────────
    try:
        ast.parse(new)
        notes.append("✓ ast.parse OK")
    except SyntaxError as e:
        print("\n".join(notes))
        print(f"✗ ABORT — post-patch syntax error: {e}. Nothing written.")
        return 1

    # ── Write ───────────────────────────────────────────────────────
    if not dry_run:
        bak = MCP.with_suffix(MCP.suffix + f".bak.{BAK_TAG}")
        shutil.copy2(MCP, bak)
        MCP.write_text(new)
        notes.append(f"  wrote {MCP.name}, backup → {bak.name}")
    else:
        notes.append("  [dry-run] would write")

    print("\n".join(notes))
    print()
    print("DONE" if not dry_run else "DRY RUN OK — re-run with --apply to write")
    if not dry_run:
        print()
        print("Next (Moa):")
        print("  sudo systemctl restart x402watch-mcp")
        print("  then run the verification block in DEDUPE_FIX_DEPLOY.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
