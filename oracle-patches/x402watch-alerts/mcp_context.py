"""
FastMCP request-context extraction for x402watch.

Permanent location on Oracle: /home/ubuntu/x402watch/app/mcp_context.py

v2 (2026-05-19): FastMCP 3.2.4 does NOT expose streamable_http_app().
The earlier ASGI-middleware approach (v1) failed at startup with
AttributeError. v2 switches to FastMCP's documented `Context`
injection: each tool adds a `ctx: Context = None` parameter that
FastMCP populates per request. This module just provides the
defensive extractor.

FastMCP excludes parameters annotated `Context` from the JSON-RPC
input schema, so the visible tool definition (what Cursor / Claude
Desktop / Smithery see) is unchanged.

Defensive extraction
--------------------
`extract_request_info(ctx)` tolerates every degraded case:
  - ctx is None (caller forgot to forward, or unit-test path)
  - ctx.request_context missing (older FastMCP, stdio transport)
  - ctx.request_context.request is None (non-HTTP transport)
  - headers missing user-agent
  - request.client is None
Anything missing → empty string → classifier downgrades to Tier 0
unknown, never raises.

IP precedence matches app/api.py's _client_ip() so HTTP and MCP
layers report the same IP for the same caller.
"""
from __future__ import annotations

import logging
from typing import Any, Tuple

log = logging.getLogger("mcp_context")


def _safe_header_get(headers: Any, name: str) -> str:
    """Header containers vary across Starlette versions and transports.
    Some are case-insensitive dicts, some are Mapping[str, str], some
    are raw tuples. Try the common shapes; fall back to empty."""
    if headers is None:
        return ""
    try:
        # Starlette Headers / dict / case-insensitive Headers
        v = headers.get(name)
        if v:
            return v
        v = headers.get(name.lower())
        if v:
            return v
    except Exception:
        pass
    # Raw list of (name, value) tuples — bytes or str.
    try:
        wanted_lower = name.lower().encode("latin-1")
        for k, v in headers:
            if isinstance(k, bytes):
                if k.lower() == wanted_lower:
                    return v.decode("latin-1", errors="replace") if isinstance(v, bytes) else str(v)
            else:
                if k.lower() == name.lower():
                    return v if isinstance(v, str) else str(v)
    except Exception:
        pass
    return ""


def extract_request_info(ctx: Any) -> Tuple[str, str]:
    """Return (user_agent, client_ip) from a FastMCP Context.

    All failure modes degrade to ("", "") — never raises into the
    caller. Safe to use unconditionally inside @mcp.tool functions.
    """
    if ctx is None:
        return "", ""

    # FastMCP nests the underlying Starlette/HTTP request under
    # ctx.request_context.request on HTTP transports. The exact path
    # has shifted across 3.x minor versions — try the common ones.
    req = None
    for attr_path in (
        ("request_context", "request"),
        ("request_context", "_request"),
        ("request",),
    ):
        cur = ctx
        try:
            for a in attr_path:
                cur = getattr(cur, a)
            if cur is not None:
                req = cur
                break
        except AttributeError:
            continue
        except Exception:
            continue
    if req is None:
        return "", ""

    headers = getattr(req, "headers", None)
    ua = _safe_header_get(headers, "user-agent")

    # IP precedence: CF > XFF > X-Real-IP > scope client (matches
    # app/api.py:_client_ip so alerts converge on the same address).
    ip = _safe_header_get(headers, "cf-connecting-ip").strip()
    if not ip:
        xff = _safe_header_get(headers, "x-forwarded-for")
        if xff:
            ip = xff.split(",")[0].strip()
    if not ip:
        ip = _safe_header_get(headers, "x-real-ip").strip()
    if not ip:
        client = getattr(req, "client", None)
        if client is not None:
            host = getattr(client, "host", None)
            if host:
                ip = host

    return ua or "", ip or ""


__all__ = ["extract_request_info"]
