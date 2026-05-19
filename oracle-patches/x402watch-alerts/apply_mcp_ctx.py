#!/usr/bin/env python3
"""
Wire FastMCP HTTP request context into x402watch MCP tool tracking.

Permanent location: /home/ubuntu/x402watch/scripts/apply_mcp_ctx.py

Background — when we shipped Step 4+5 wireup, `_track()` couldn't reach
the request's User-Agent / IP, so every MCP call landed in stats.jsonl
as Tier 0 ("unknown UA") regardless of whether it came from Cursor,
Smithery, or a generic crawler. The TODO comment in `_track()` notes
"FastMCP ctx unavailable in tool scope" — that was incorrect on closer
inspection. FastMCP installs a `RequestContextMiddleware` at the
outermost layer of every HTTP transport, and `fastmcp.server.dependencies
.get_http_request()` exposes the current `starlette.requests.Request`
to any callable executing inside a tool invocation. No ASGI plumbing
or Context-parameter injection required.

This patcher rewires `_track()` to:
  1. Pull the live Request via `get_http_request()` (guarded — falls
     back to empty strings if the helper isn't available in older
     FastMCP versions or if we're outside an HTTP scope).
  2. Read `user-agent` from request headers.
  3. Read client IP, preferring `x-forwarded-for` / `x-real-ip` /
     `cf-connecting-ip` over `request.client.host` so the value
     reflects the real caller behind nginx.
  4. Pass both into `_stats_write()` and `_notify_mcp_tool()` so the
     ClientClassifier can finally produce real tier classifications
     ("Cursor IDE" → T2, "smithery-scanner" → T4, etc.).

Apply with:
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/apply_mcp_ctx.py            # dry-run
    venv/bin/python scripts/apply_mcp_ctx.py --apply    # write + verify

Idempotent — repeated `--apply` is a no-op (checks the replacement-
already-present path before the anchor-match path, same convention
as apply_wireup.py).
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
BAK_TAG = "mcp-ctx-" + datetime.now(KST).strftime("%Y%m%d-%H%M")


PATCHES = [
    # (1) Import the FastMCP HTTP-request accessor. Guard with
    # try/except in case Moa runs an older FastMCP where dependencies
    # lives at a different path.
    (
        "# x402watch alerts hardening — additive imports\n"
        "from app._stats import write as _stats_write\n"
        "from app.client_classifier import classify as _classify\n"
        "from app.telegram_notify import notify_mcp_tool as _notify_mcp_tool\n"
        "from app.mcp_payment_hint import FREE_TOOL_TAGLINE as _FREE_TAGLINE  # noqa: F401\n",
        "# x402watch alerts hardening — additive imports\n"
        "from app._stats import write as _stats_write\n"
        "from app.client_classifier import classify as _classify\n"
        "from app.telegram_notify import notify_mcp_tool as _notify_mcp_tool\n"
        "from app.mcp_payment_hint import FREE_TOOL_TAGLINE as _FREE_TAGLINE  # noqa: F401\n"
        "# x402watch alerts hardening v2 — FastMCP request-context accessor.\n"
        "# Public since FastMCP 2.x; lives in fastmcp.server.dependencies.\n"
        "try:\n"
        "    from fastmcp.server.dependencies import get_http_request as _get_http_request\n"
        "except Exception:  # pragma: no cover\n"
        "    _get_http_request = None  # type: ignore[assignment]\n",
    ),
    # (2) Replace _track() — pull UA + IP from get_http_request().
    # Anchors on the exact body shipped by apply_wireup.py so we don't
    # mistake an unrelated function for _track.
    (
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
        "def _track(tool_name: str) -> None:\n"
        "    # x402watch alerts hardening v2 — pull live UA + IP from the\n"
        "    # FastMCP-installed RequestContextMiddleware. get_http_request()\n"
        "    # raises RuntimeError when there is no HTTP scope (e.g. local\n"
        "    # invocation in a unit test); treat that as Tier 0 unknown.\n"
        "    ua = \"\"\n"
        "    ip = \"\"\n"
        "    if _get_http_request is not None:\n"
        "        try:\n"
        "            _req = _get_http_request()\n"
        "            ua = _req.headers.get(\"user-agent\", \"\") or \"\"\n"
        "            # Prefer the proxy-supplied client IP over scope.client,\n"
        "            # so the value reflects the real caller behind nginx.\n"
        "            xff = _req.headers.get(\"x-forwarded-for\", \"\")\n"
        "            ip = (\n"
        "                xff.split(\",\")[0].strip()\n"
        "                or _req.headers.get(\"x-real-ip\", \"\").strip()\n"
        "                or _req.headers.get(\"cf-connecting-ip\", \"\").strip()\n"
        "                or (_req.client.host if _req.client else \"\")\n"
        "            )\n"
        "        except RuntimeError:\n"
        "            pass  # not inside an HTTP request — fall through to empties\n"
        "        except Exception:\n"
        "            pass  # defensive: never let stats break the tool\n"
        "    # Always-on stats for the daily digest.\n"
        "    _stats_write({\n"
        "        \"kind\": \"mcp_call\",\n"
        "        \"tool\": tool_name,\n"
        "        \"is_paid_tool\": False,\n"
        "        \"ua\": ua,\n"
        "        \"ip\": ip,\n"
        "    })\n"
        "    # Tier-aware alert.\n"
        "    asyncio.create_task(_notify_mcp_tool(\n"
        "        tool_name=tool_name,\n"
        "        classification=_classify(ua),\n"
        "        ip=ip, user_agent=ua,\n"
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


def apply(path: Path, patches, dry_run: bool):
    if not path.exists():
        return False, [f"  ✗ missing: {path}"]
    src = path.read_text()
    new = src
    notes = []
    for anchor, replacement in patches:
        # replacement-presence check first so additive patches stay idempotent
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

    print(f"== mcp ctx wireup — {'APPLY' if not dry_run else 'DRY RUN'} ==")
    print(f"   target = {MCP}")
    print()
    ok, notes = apply(MCP, PATCHES, dry_run)
    print("\n".join(notes))
    if not ok:
        print()
        print("FAIL — at least one anchor not found. Nothing written.")
        print("       (apply_wireup.py must run first to set up the anchors.)")
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
