#!/usr/bin/env python3
"""
Apply x402watch alerts wireup — Steps 4 + 5 (A.1 Option 1, B.3).

Permanent location: /home/ubuntu/x402watch/scripts/apply_wireup.py

Edits made (idempotent — re-running prints "already applied"):

  app/api.py
    1. +2 imports next to the telegram block
       (_stats.write, telegram_notify.notify_post_settle_failure)
    2. +stats.jsonl write inside _enrich_and_notify (after _format_alert,
       so we record the same numbers the alert sees; non-owner path only)
    3. +post-settle failure clause at the top of payment_notify_middleware
       — fires when status >= 500 AND request has X-Payment header

  app/mcp_server.py
    1. +4 imports (_stats, classify, notify_mcp_tool, FREE_TAGLINE)
    2. Replace _track() body — stats.jsonl write + tier-aware alert
       fired alongside the existing cooldown-gated _tg_notify
    3. Append FREE_TOOL_TAGLINE to all 5 tool docstrings

Hard invariants the patcher guards:
  - app/api.py's final non-blank, non-comment line stays
    `app = X402ResourceRewriter(app)`
  - both files still parse as Python after the edit
  - no anchor missing → bail with FAIL, write nothing

Usage:
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/apply_wireup.py            # dry-run
    venv/bin/python scripts/apply_wireup.py --apply    # write + verify

Re-running with --apply on an already-patched tree is safe (every
anchor includes the freshly-added text so it stops matching).
"""
from __future__ import annotations

import argparse
import ast
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/ubuntu/x402watch")
API = ROOT / "app" / "api.py"
MCP = ROOT / "app" / "mcp_server.py"
KST = timezone(timedelta(hours=9))
BAK_TAG = "alerts-wireup-" + datetime.now(KST).strftime("%Y%m%d-%H%M")
WRAPPER_TAIL = "app = X402ResourceRewriter(app)"


# ─── api.py patches ──────────────────────────────────────────────────
API_PATCHES = [
    # (1) Imports — appended right after the existing telegram-block imports.
    (
        "import httpx as _httpx_tg\nfrom fastapi import Request as _Request_tg\n",
        "import httpx as _httpx_tg\n"
        "from fastapi import Request as _Request_tg\n"
        "# x402watch alerts hardening — additive imports\n"
        "from app._stats import write as _stats_write\n"
        "from app.telegram_notify import notify_post_settle_failure as _notify_post_settle\n",
    ),
    # (2) stats.jsonl write inside _enrich_and_notify (non-owner path).
    #     Anchored on the two-line pair right before await _tg_send(text).
    (
        "            ipinfo = await _ipinfo(ip, redis_client)\n"
        "            text = _format_alert(endpoint_label, amount, ip, ipinfo, stats)\n",
        "            ipinfo = await _ipinfo(ip, redis_client)\n"
        "            text = _format_alert(endpoint_label, amount, ip, ipinfo, stats)\n"
        "            _stats_write({\n"
        "                \"kind\": \"payment\",\n"
        "                \"endpoint\": endpoint_label,\n"
        "                \"amount_usd\": amount,\n"
        "                \"ip\": ip,\n"
        "                \"ipinfo\": ipinfo,\n"
        "                \"total_count\": stats.get(\"total_count\"),\n"
        "                \"daily_count\": stats.get(\"daily_count\"),\n"
        "            })\n",
    ),
    # (3) Post-settle failure clause — slips in right above the existing
    #     `if matched is None or response.status_code != 200: return response`.
    (
        "    response = await call_next(request)\n"
        "    matched = _match_paid(request.url.path, request.method)\n"
        "    if matched is None or response.status_code != 200:\n"
        "        return response\n",
        "    response = await call_next(request)\n"
        "    matched = _match_paid(request.url.path, request.method)\n"
        "    # x402watch alerts hardening — post-settle failure:\n"
        "    # 5xx after X-Payment means we may have settled then failed to honour.\n"
        "    if matched is not None and response.status_code >= 500 \\\n"
        "            and request.headers.get(\"x-payment\"):\n"
        "        _endpoint_label, _amount = matched\n"
        "        _ip = _client_ip(request)\n"
        "        _stats_write({\n"
        "            \"kind\": \"post_settle_fail\",\n"
        "            \"endpoint\": _endpoint_label,\n"
        "            \"status\": response.status_code,\n"
        "            \"ip\": _ip,\n"
        "            \"amount_usd\": _amount,\n"
        "        })\n"
        "        _asyncio_tg.create_task(_notify_post_settle(\n"
        "            endpoint=_endpoint_label,\n"
        "            status=response.status_code,\n"
        "            ip=_ip,\n"
        "            payer_wallet=None,\n"
        "            tx_hash=None,\n"
        "            amount_usd=_amount,\n"
        "        ))\n"
        "        return response\n"
        "    if matched is None or response.status_code != 200:\n"
        "        return response\n",
    ),
]


# ─── mcp_server.py core patches ──────────────────────────────────────
MCP_PATCHES = [
    # (1) Imports next to existing fastmcp imports.
    (
        "from fastmcp import FastMCP\nfrom pydantic import Field\n",
        "from fastmcp import FastMCP\n"
        "from pydantic import Field\n\n"
        "# x402watch alerts hardening — additive imports\n"
        "from app._stats import write as _stats_write\n"
        "from app.client_classifier import classify as _classify\n"
        "from app.telegram_notify import notify_mcp_tool as _notify_mcp_tool\n"
        "from app.mcp_payment_hint import FREE_TOOL_TAGLINE as _FREE_TAGLINE  # noqa: F401\n",
    ),
    # (2) _track() — keep existing cooldown alert, add stats + tier alert.
    (
        "def _track(tool_name: str) -> None:\n"
        "    now = time.monotonic()\n"
        "    if now - _last_notified.get(tool_name, 0) < _NOTIFY_COOLDOWN_SECONDS:\n"
        "        return\n"
        "    _last_notified[tool_name] = now\n"
        "    asyncio.create_task(_tg_notify(f\"x402watch MCP: {tool_name}\"))\n",
        "def _track(tool_name: str) -> None:\n"
        "    # x402watch alerts hardening — always-on stats for the daily digest.\n"
        "    _stats_write({\n"
        "        \"kind\": \"mcp_call\",\n"
        "        \"tool\": tool_name,\n"
        "        \"is_paid_tool\": False,\n"
        "        \"ua\": \"\",  # FastMCP ctx unavailable in tool scope — see TODO\n"
        "        \"ip\": \"\",\n"
        "    })\n"
        "    # Tier-aware alert (T0 unknown until UA wiring lands — fires the\n"
        "    # first-seen-per-24h path, then dedup-silent).\n"
        "    asyncio.create_task(_notify_mcp_tool(\n"
        "        tool_name=tool_name,\n"
        "        classification=_classify(\"\"),\n"
        "        ip=\"\", user_agent=\"\",\n"
        "        is_paid_tool=False,\n"
        "    ))\n"
        "    # Existing cooldown-gated alert preserved verbatim.\n"
        "    now = time.monotonic()\n"
        "    if now - _last_notified.get(tool_name, 0) < _NOTIFY_COOLDOWN_SECONDS:\n"
        "        return\n"
        "    _last_notified[tool_name] = now\n"
        "    asyncio.create_task(_tg_notify(f\"x402watch MCP: {tool_name}\"))\n",
    ),
]


# ─── Free-tool tagline (5 docstrings) ────────────────────────────────
FREE_TAGLINE = (
    "\n    Free tier. No payment required. Returns wash-filtered data using the\n"
    "    same v2.0 algorithm as the paid endpoints.\n    "
)

MCP_TOOL_PATCHES = [
    (
        "    before drilling into specific services or wallets.\n    \"\"\"\n    _track(\"x402_get_categories\")",
        "    before drilling into specific services or wallets." + FREE_TAGLINE
        + "\"\"\"\n    _track(\"x402_get_categories\")",
    ),
    (
        "    Use this to evaluate a single service's traffic composition.\n    \"\"\"\n    _track(\"x402_get_service\")",
        "    Use this to evaluate a single service's traffic composition." + FREE_TAGLINE
        + "\"\"\"\n    _track(\"x402_get_service\")",
    ),
    (
        "    HTTP round-trip.\n    \"\"\"\n    _track(\"x402_check_wash\")",
        "    HTTP round-trip." + FREE_TAGLINE
        + "\"\"\"\n    _track(\"x402_check_wash\")",
    ),
    (
        "    mix. Use this to find services by topic, chain, or seller wallet.\n    \"\"\"\n    _track(\"x402_search_services\")",
        "    mix. Use this to find services by topic, chain, or seller wallet." + FREE_TAGLINE
        + "\"\"\"\n    _track(\"x402_search_services\")",
    ),
    (
        "    surges (>= 100 24h tx and >= +50% growth). Refreshed every 5 min.\n    \"\"\"\n    _track(\"x402_get_trends\")",
        "    surges (>= 100 24h tx and >= +50% growth). Refreshed every 5 min." + FREE_TAGLINE
        + "\"\"\"\n    _track(\"x402_get_trends\")",
    ),
]


# ─── Patcher core ────────────────────────────────────────────────────
def apply(path: Path, patches, dry_run: bool) -> tuple[bool, list[str]]:
    if not path.exists():
        return False, [f"  ✗ missing: {path}"]
    src = path.read_text()
    new = src
    notes = []
    for anchor, replacement in patches:
        # Check `replacement in src` BEFORE `anchor in src` — several
        # replacements INCLUDE the anchor verbatim (additive patches),
        # so the anchor check would otherwise spuriously match on a
        # second run and duplicate lines.
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


def verify_wrapper_last() -> bool:
    for line in reversed(API.read_text().splitlines()):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        return s == WRAPPER_TAIL
    return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="write changes (default: dry-run)")
    args = p.parse_args()
    dry_run = not args.apply

    print(f"== x402watch alerts wireup — {'APPLY' if not dry_run else 'DRY RUN'} ==")
    print(f"   api.py        = {API}")
    print(f"   mcp_server.py = {MCP}")
    print()

    ok = True

    print("[api.py] core patches:")
    a_ok, notes = apply(API, API_PATCHES, dry_run)
    print("\n".join(notes))
    ok &= a_ok

    print()
    print("[mcp_server.py] core patches:")
    m_ok, notes = apply(MCP, MCP_PATCHES, dry_run)
    print("\n".join(notes))
    ok &= m_ok

    print()
    print("[mcp_server.py] free-tool tagline (5 docstrings):")
    t_ok, notes = apply(MCP, MCP_TOOL_PATCHES, dry_run)
    print("\n".join(notes))
    ok &= t_ok

    if not ok:
        print()
        print("FAIL — at least one anchor not found. Nothing was written.")
        return 1

    if not dry_run:
        print()
        print("=== Post-apply verification ===")
        try:
            ast.parse(API.read_text())
            print("[OK] api.py parses")
        except SyntaxError as e:
            print(f"[FAIL] api.py syntax: {e}")
            return 1
        try:
            ast.parse(MCP.read_text())
            print("[OK] mcp_server.py parses")
        except SyntaxError as e:
            print(f"[FAIL] mcp_server.py syntax: {e}")
            return 1
        if not verify_wrapper_last():
            print("[FAIL] api.py last code line is no longer X402ResourceRewriter(app)")
            return 1
        print("[OK] api.py wrapper invariant intact")

    print()
    print("DONE" if not dry_run else "DRY RUN OK — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
