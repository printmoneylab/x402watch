#!/usr/bin/env python3
"""
Apply FastMCP request-context extraction to app/mcp_server.py.

Permanent location: /home/ubuntu/x402watch/scripts/apply_mcp_context.py

Three edits, all idempotent:

  1. +import line for the two contextvar getters
  2. _track() reads UA/IP from contextvars and passes them to the
     stats write + notify_mcp_tool call (was empty string before).
  3. The `if __name__ == "__main__":` block changes from
        mcp.run(transport="streamable-http", ...)
     to
        app = MCPRequestContextMiddleware(mcp.streamable_http_app(path="/mcp"))
        uvicorn.run(app, host=..., port=port)
     so the contextvar middleware actually wraps the ASGI app.

Pre-flight:
  - Confirm FastMCP 3.x exposes `streamable_http_app`. If your version
    uses a different accessor (`http_app`, `sse_app`, etc.) the
    `if __name__` patch will fail with "ANCHOR MISSING" instead of
    silently writing broken code — investigate before re-running.

Usage:
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/apply_mcp_context.py           # dry-run
    venv/bin/python scripts/apply_mcp_context.py --apply   # write + verify

Rollback: each --apply writes a timestamped .bak.mcp-context-* file.
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
BAK_TAG = "mcp-context-" + datetime.now(KST).strftime("%Y%m%d-%H%M")


# (1) Imports — placed right after the existing alerts-wireup imports.
PATCH_IMPORTS = (
    "from app.mcp_payment_hint import FREE_TOOL_TAGLINE as _FREE_TAGLINE  # noqa: F401\n",
    "from app.mcp_payment_hint import FREE_TOOL_TAGLINE as _FREE_TAGLINE  # noqa: F401\n"
    "# FastMCP context bridge — read real UA/IP per request via contextvars.\n"
    "from app.mcp_context import (\n"
    "    MCPRequestContextMiddleware as _MCPCtxMW,\n"
    "    get_request_ua as _get_ua,\n"
    "    get_request_ip as _get_ip,\n"
    ")\n"
    "import uvicorn as _uvicorn\n",
)


# (2) _track() — replace the empty-string UA/IP with contextvar reads.
PATCH_TRACK = (
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
    "    _ua = _get_ua()\n"
    "    _ip = _get_ip()\n"
    "    _stats_write({\n"
    "        \"kind\": \"mcp_call\",\n"
    "        \"tool\": tool_name,\n"
    "        \"is_paid_tool\": False,\n"
    "        \"ua\": _ua,\n"
    "        \"ip\": _ip,\n"
    "    })\n"
    "    # Tier-aware alert — real UA from contextvar populated by\n"
    "    # MCPRequestContextMiddleware. T0 fallback if the middleware\n"
    "    # ever fails to populate (graceful degradation).\n"
    "    asyncio.create_task(_notify_mcp_tool(\n"
    "        tool_name=tool_name,\n"
    "        classification=_classify(_ua),\n"
    "        ip=_ip, user_agent=_ua,\n"
    "        is_paid_tool=False,\n"
    "    ))\n",
)


# (3) Runner — replace mcp.run() with explicit uvicorn.run() of the
#     wrapped ASGI app. Anchors on the full block so we don't match
#     and re-wrap on a re-run.
PATCH_RUNNER = (
    "if __name__ == \"__main__\":\n"
    "    port = int(os.environ.get(\"MCP_PORT\", \"8453\"))\n"
    "    log.info(\"x402watch MCP starting on 0.0.0.0:%d (transport=streamable-http, path=/mcp)\", port)\n"
    "    mcp.run(transport=\"streamable-http\", host=\"0.0.0.0\", port=port, path=\"/mcp\")\n",
    "if __name__ == \"__main__\":\n"
    "    port = int(os.environ.get(\"MCP_PORT\", \"8453\"))\n"
    "    log.info(\"x402watch MCP starting on 0.0.0.0:%d (transport=streamable-http, path=/mcp, ctx=on)\", port)\n"
    "    # Wrap FastMCP's ASGI app with the context-extracting middleware\n"
    "    # so _track() sees real UA / IP per request. If FastMCP renames\n"
    "    # streamable_http_app() in a future version, fall back to\n"
    "    # mcp.run(...) (graceful degrade — Tier 0 unknown).\n"
    "    _asgi_app = mcp.streamable_http_app(path=\"/mcp\")\n"
    "    _asgi_app = _MCPCtxMW(_asgi_app)\n"
    "    _uvicorn.run(_asgi_app, host=\"0.0.0.0\", port=port)\n",
)


PATCHES = [PATCH_IMPORTS, PATCH_TRACK, PATCH_RUNNER]


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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true",
                   help="write changes (default: dry-run)")
    args = p.parse_args()
    dry_run = not args.apply

    print(f"== FastMCP context bridge — {'APPLY' if not dry_run else 'DRY RUN'} ==")
    print(f"   target: {MCP}")
    print()

    ok, notes = apply(MCP, PATCHES, dry_run)
    print("\n".join(notes))

    if not ok:
        print()
        print("FAIL — at least one anchor not found.")
        print("If your FastMCP version doesn't expose streamable_http_app(),")
        print("inspect: venv/bin/python -c 'import fastmcp; help(fastmcp.FastMCP)'")
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
