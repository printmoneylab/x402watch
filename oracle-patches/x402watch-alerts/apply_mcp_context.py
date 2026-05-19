#!/usr/bin/env python3
"""
Apply FastMCP Context injection to app/mcp_server.py.

Permanent location: /home/ubuntu/x402watch/scripts/apply_mcp_context.py

v2 (2026-05-19) — replaces the v1 ASGI-middleware approach that broke
on FastMCP 3.2.4 (no streamable_http_app()). v2 uses FastMCP's
documented Context injection: each tool gets a `ctx: Context = None`
parameter, FastMCP fills it per request, and our helper extracts
UA / IP from it.

The Context type annotation excludes the parameter from the JSON-RPC
input schema, so clients (Cursor / Smithery / Claude Desktop) see the
exact same tool signatures as before.

Twelve idempotent patches:
  1. +imports: Context (from fastmcp) + extract_request_info
  2. _track() body: reads ua/ip from ctx, passes to classifier + alerter
  3-7. Five tool signatures gain `ctx: Context = None`
  8-12. Five _track call sites pass `ctx=ctx`

Anchor strategy: replacement-string-in-source checked BEFORE anchor
match, same as apply_wireup.py. Re-runs are no-ops; missing anchor
bails the whole apply (no partial writes).

Pre-flight:
    venv/bin/python -c 'from fastmcp import Context; print(Context)'
    # must succeed before --apply

Usage:
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/apply_mcp_context.py            # dry-run
    venv/bin/python scripts/apply_mcp_context.py --apply    # write

Rollback: each --apply leaves a .bak.mcp-context-v2-* timestamped backup.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/home/ubuntu/x402watch")
MCP = ROOT / "app" / "mcp_server.py"
KST = timezone(timedelta(hours=9))
BAK_TAG = "mcp-context-v2-" + datetime.now(KST).strftime("%Y%m%d-%H%M")


# (1) Imports — appended to the alerts-wireup import block.
PATCH_IMPORTS = (
    "from app.mcp_payment_hint import FREE_TOOL_TAGLINE as _FREE_TAGLINE  # noqa: F401\n",
    "from app.mcp_payment_hint import FREE_TOOL_TAGLINE as _FREE_TAGLINE  # noqa: F401\n"
    "# FastMCP Context injection — tool funcs gain ctx: Context = None,\n"
    "# FastMCP fills it per request; extract_request_info pulls UA + IP.\n"
    "from fastmcp import Context\n"
    "from app.mcp_context import extract_request_info as _extract_request_info\n",
)


# (2) _track() body — pull ua/ip from ctx instead of using empty strings.
PATCH_TRACK = (
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
    "    ))\n",
    "def _track(tool_name: str, ctx=None) -> None:\n"
    "    # x402watch alerts hardening — always-on stats for the daily digest.\n"
    "    # ctx is the FastMCP Context (or None when caller didn't forward it);\n"
    "    # extract_request_info degrades to (\"\",\"\") if anything is missing.\n"
    "    _ua, _ip = _extract_request_info(ctx)\n"
    "    _stats_write({\n"
    "        \"kind\": \"mcp_call\",\n"
    "        \"tool\": tool_name,\n"
    "        \"is_paid_tool\": False,\n"
    "        \"ua\": _ua,\n"
    "        \"ip\": _ip,\n"
    "    })\n"
    "    # Tier-aware alert — real UA from the per-request FastMCP Context.\n"
    "    # T0 fallback if ctx is None or strips out (graceful degradation).\n"
    "    asyncio.create_task(_notify_mcp_tool(\n"
    "        tool_name=tool_name,\n"
    "        classification=_classify(_ua),\n"
    "        ip=_ip, user_agent=_ua,\n"
    "        is_paid_tool=False,\n"
    "    ))\n",
)


# (3-7) Tool signatures — add `ctx: Context = None` parameter.
# Anchors are unique per tool because each closes with a distinct
# combination of preceding text + `) -> dict:`.
PATCH_SIG_CATEGORIES = (
    "async def x402_get_categories() -> dict:\n",
    "async def x402_get_categories(ctx: Context = None) -> dict:\n",
)
PATCH_SIG_SERVICE = (
    "async def x402_get_service(\n"
    "    service_id: int = Field(\n"
    "        description=\"Numeric x402 service id (visible in /services list and detail URLs).\"\n"
    "    ),\n"
    ") -> dict:\n",
    "async def x402_get_service(\n"
    "    service_id: int = Field(\n"
    "        description=\"Numeric x402 service id (visible in /services list and detail URLs).\"\n"
    "    ),\n"
    "    ctx: Context = None,\n"
    ") -> dict:\n",
)
PATCH_SIG_WASH = (
    "async def x402_check_wash(\n"
    "    address: str = Field(\n"
    "        default=\"\",\n"
    "        description=\"Optional wallet or seller address. When provided, the response includes a hint about the paid per-address endpoint.\",\n"
    "    ),\n"
    ") -> dict:\n",
    "async def x402_check_wash(\n"
    "    address: str = Field(\n"
    "        default=\"\",\n"
    "        description=\"Optional wallet or seller address. When provided, the response includes a hint about the paid per-address endpoint.\",\n"
    "    ),\n"
    "    ctx: Context = None,\n"
    ") -> dict:\n",
)
PATCH_SIG_SEARCH = (
    "    page_size: int = Field(\n"
    "        default=24, description=\"Page size (max 200; default 24).\"\n"
    "    ),\n"
    ") -> dict:\n",
    "    page_size: int = Field(\n"
    "        default=24, description=\"Page size (max 200; default 24).\"\n"
    "    ),\n"
    "    ctx: Context = None,\n"
    ") -> dict:\n",
)
PATCH_SIG_TRENDS = (
    "async def x402_get_trends() -> dict:\n",
    "async def x402_get_trends(ctx: Context = None) -> dict:\n",
)


# (8-12) _track call sites — pass ctx=ctx.
PATCH_CALL_CATEGORIES = (
    "    _track(\"x402_get_categories\")\n",
    "    _track(\"x402_get_categories\", ctx=ctx)\n",
)
PATCH_CALL_SERVICE = (
    "    _track(\"x402_get_service\")\n",
    "    _track(\"x402_get_service\", ctx=ctx)\n",
)
PATCH_CALL_WASH = (
    "    _track(\"x402_check_wash\")\n",
    "    _track(\"x402_check_wash\", ctx=ctx)\n",
)
PATCH_CALL_SEARCH = (
    "    _track(\"x402_search_services\")\n",
    "    _track(\"x402_search_services\", ctx=ctx)\n",
)
PATCH_CALL_TRENDS = (
    "    _track(\"x402_get_trends\")\n",
    "    _track(\"x402_get_trends\", ctx=ctx)\n",
)


PATCHES = [
    PATCH_IMPORTS,
    PATCH_TRACK,
    PATCH_SIG_CATEGORIES,
    PATCH_SIG_SERVICE,
    PATCH_SIG_WASH,
    PATCH_SIG_SEARCH,
    PATCH_SIG_TRENDS,
    PATCH_CALL_CATEGORIES,
    PATCH_CALL_SERVICE,
    PATCH_CALL_WASH,
    PATCH_CALL_SEARCH,
    PATCH_CALL_TRENDS,
]


def apply(path: Path, patches, dry_run: bool):
    if not path.exists():
        return False, [f"  ✗ missing: {path}"]
    src = path.read_text()
    new = src
    notes = []
    for anchor, replacement in patches:
        if replacement in new:
            notes.append(f"  ◌ already applied ({anchor.strip()[:60]}…)")
        elif anchor in new:
            new = new.replace(anchor, replacement, 1)
            notes.append(f"  ✓ matched ({anchor.strip()[:60]}…)")
        else:
            notes.append(f"  ✗ ANCHOR MISSING: {anchor.strip()[:80]}…")
            return False, notes
    if new == src:
        return True, notes + ["  (no changes — already applied)"]
    if not dry_run:
        bak = path.with_suffix(path.suffix + f".bak.{BAK_TAG}")
        shutil.copy2(path, bak)
        path.write_text(new)
        notes.append(f"  wrote {path.name}, backup → {bak.name}")
    else:
        notes.append("  [dry-run] would write")
    return True, notes


def preflight() -> bool:
    """Sanity-check fastmcp.Context import. Without this, --apply would
    write a file that fails to start with ImportError."""
    try:
        sys.path.insert(0, str(ROOT))
        from fastmcp import Context  # noqa: F401
        return True
    except Exception as e:
        print(f"  ✗ preflight FAILED: cannot import fastmcp.Context: {e}")
        print("    The patcher would write code that fails on import.")
        print("    Investigate before retrying. Hint:")
        print("      venv/bin/python -c 'import fastmcp; print(dir(fastmcp))'")
        return False


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="write changes (default: dry-run)")
    p.add_argument("--skip-preflight", action="store_true",
                   help="bypass fastmcp.Context import check")
    args = p.parse_args()
    dry_run = not args.apply

    print(f"== FastMCP Context injection — {'APPLY' if not dry_run else 'DRY RUN'} (v2) ==")
    print(f"   target: {MCP}")
    print()

    if not args.skip_preflight:
        print("[preflight] fastmcp.Context import")
        if not preflight():
            return 2
        print("  ✓ Context import OK")
        print()

    ok, notes = apply(MCP, PATCHES, dry_run)
    print("\n".join(notes))

    if not ok:
        print()
        print("FAIL — at least one anchor not found. Nothing written.")
        return 1

    if not dry_run:
        try:
            ast.parse(MCP.read_text())
            print("[OK] mcp_server.py parses")
        except SyntaxError as e:
            print(f"[FAIL] mcp_server.py syntax: {e}")
            return 1

    print()
    print("DONE" if not dry_run else "DRY RUN OK — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
