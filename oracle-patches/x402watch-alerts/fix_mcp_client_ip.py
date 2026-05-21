#!/usr/bin/env python3
"""
Fix MCP client-IP attribution — reorder _track()'s IP priority so the
Cloudflare-supplied real client IP wins over the X-Forwarded-For chain.

Permanent location: /home/ubuntu/x402watch/scripts/fix_mcp_client_ip.py

The bug
=======
stats.jsonl mcp_call rows record `ip` as a Cloudflare *edge* IP
(e.g. 104.22.31.138) instead of the real visitor. Nginx's own access
log shows the true client (e.g. 212.11.41.202), so the real IP DOES
reach the box — it just loses the priority race inside `_track()`.

apply_mcp_ctx.py built `_track()` with this order:

    xff = _req.headers.get("x-forwarded-for", "")
    ip = (
        xff.split(",")[0].strip()                           # ← 1st: WRONG behind CF
        or _req.headers.get("x-real-ip", "").strip()
        or _req.headers.get("cf-connecting-ip", "").strip()  # ← real IP, but 3rd
        or (_req.client.host if _req.client else "")
    )

Behind Cloudflare, `X-Forwarded-For[0]` is not a trustworthy visitor
IP — the chain can start with a CF edge address (or a client-spoofed
value CF prepends to). Cloudflare's *contract* is `CF-Connecting-IP`:
it always carries the real visitor IP. The fix is to consult it first.

Code precedent: app/api.py's `_client_ip()` ALREADY does
cf-connecting-ip first — the FastAPI side is correct; only the MCP
side regressed. This patch makes `_track()` consistent with it.

The fix
=======
Reorder to:  cf-connecting-ip  →  x-real-ip  →  x-forwarded-for[0]  →  client.host

uvicorn note: uvicorn's `proxy_headers` / `forwarded_allow_ips` only
rewrite `request.client.host`. They do NOT add or remove request
headers — `_track()` reads the headers directly, so no uvicorn / ASGI
option change is needed. This is a pure priority reorder.

Usage
=====
    cd /home/ubuntu/x402watch
    venv/bin/python scripts/fix_mcp_client_ip.py            # dry-run
    venv/bin/python scripts/fix_mcp_client_ip.py --apply    # write

Idempotent (re-apply detects the reordered block and exits 0).
Backup at mcp_server.py.bak.cf-ip-fix-YYYYMMDD-HHMM (KST).
ast.parse() gate before any write.

Scope: app/mcp_server.py only. Restart x402watch-mcp.service only.
This patch alone is sufficient IF Nginx forwards CF-Connecting-IP to
the backend (it does by default — the header has no underscore, so
Nginx passes it through unless a proxy_set_header overrides it). If
Step 1 of CF_IP_FIX_DEPLOY.md shows Nginx is NOT forwarding it, also
apply the Nginx scenario-A fix from that doc.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

MCP = Path("/home/ubuntu/x402watch/app/mcp_server.py")
KST = timezone(timedelta(hours=9))
BAK_TAG = "cf-ip-fix-" + datetime.now(KST).strftime("%Y%m%d-%H%M")

# Anchor — the exact IP-priority block apply_mcp_ctx.py emitted.
ANCHOR = (
    "            xff = _req.headers.get(\"x-forwarded-for\", \"\")\n"
    "            ip = (\n"
    "                xff.split(\",\")[0].strip()\n"
    "                or _req.headers.get(\"x-real-ip\", \"\").strip()\n"
    "                or _req.headers.get(\"cf-connecting-ip\", \"\").strip()\n"
    "                or (_req.client.host if _req.client else \"\")\n"
    "            )\n"
)

REPLACEMENT = (
    "            xff = _req.headers.get(\"x-forwarded-for\", \"\")\n"
    "            # CF client-IP fix — cf-connecting-ip is Cloudflare's\n"
    "            # contractual real-visitor header; trust it first.\n"
    "            # x-forwarded-for[0] is NOT trustworthy behind CF.\n"
    "            # Order matches app/api.py _client_ip().\n"
    "            ip = (\n"
    "                _req.headers.get(\"cf-connecting-ip\", \"\").strip()\n"
    "                or _req.headers.get(\"x-real-ip\", \"\").strip()\n"
    "                or xff.split(\",\")[0].strip()\n"
    "                or (_req.client.host if _req.client else \"\")\n"
    "            )\n"
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reorder _track() IP priority for CF")
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    args = ap.parse_args()
    dry = not args.apply

    print(f"== fix MCP client-IP priority — {'APPLY' if not dry else 'DRY RUN'} ==")
    print(f"   target: {MCP}")
    print()

    if not MCP.exists():
        print(f"FAIL — {MCP} not found")
        return 1
    src = MCP.read_text()

    if REPLACEMENT in src:
        print("◌ already patched — IP priority is already cf-connecting-ip first.")
        return 0
    if ANCHOR not in src:
        print("✗ ANCHOR MISSING — _track()'s IP block is not in the expected")
        print("  apply_mcp_ctx.py shape. Current x-forwarded-for / cf-connecting-ip")
        print("  usage in mcp_server.py:")
        for i, line in enumerate(src.splitlines(), 1):
            low = line.lower()
            if "forwarded-for" in low or "cf-connecting-ip" in low or "x-real-ip" in low:
                print(f"    L{i}: {line.rstrip()}")
        print("  Paste the current _track() body so the anchor can be regenerated.")
        return 1

    new = src.replace(ANCHOR, REPLACEMENT, 1)
    try:
        ast.parse(new)
        print("✓ IP priority reordered: cf-connecting-ip → x-real-ip → xff[0] → client.host")
        print("✓ ast.parse OK")
    except SyntaxError as e:
        print(f"FAIL — post-edit syntax error: {e}")
        return 1

    if dry:
        print()
        print("DRY RUN OK — re-run with --apply to write.")
        return 0

    bak = MCP.with_suffix(MCP.suffix + f".bak.{BAK_TAG}")
    shutil.copy2(MCP, bak)
    MCP.write_text(new)
    print()
    print(f"WROTE  {MCP}")
    print(f"BACKUP {bak}")
    print()
    print("Next: sudo systemctl restart x402watch-mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
