"""
FastMCP request-context extraction for x402watch.

Permanent location on Oracle: /home/ubuntu/x402watch/app/mcp_context.py

The MCP tool functions are plain `async def`s — they don't receive the
HTTP request object, so `_track()` was firing the classifier with an
empty User-Agent (everything → Tier 0 unknown). This module bridges
the gap with a tiny ASGI middleware that captures UA / IP from the
incoming HTTP request and stashes them in contextvars; the tool body
reads back via `get_request_ua()` / `get_request_ip()`.

Why contextvars (not Context injection)
---------------------------------------
FastMCP 3.x supports `ctx: Context` parameter injection, but adding
that parameter changes the tool's JSON-RPC schema visible to every
MCP client (Cursor, Claude Desktop, Smithery, etc.). Avoiding the
schema change keeps existing integrations stable. Contextvars stay
out of the tool signature entirely.

Why graceful degradation matters
--------------------------------
If the ASGI middleware isn't wired (or FastMCP renames its app
accessor in a future version), the contextvars stay at their default
empty strings — same behaviour as before this patch. _track() will
still write to stats.jsonl and the alert layer will still fire; tier
classification just degrades to "Tier 0 unknown UA". No regression.
"""
from __future__ import annotations

import contextvars
import logging
from typing import Iterable

log = logging.getLogger("mcp_context")


# ─── Contextvars ─────────────────────────────────────────────────────
_request_ua: contextvars.ContextVar[str] = contextvars.ContextVar(
    "x402watch.mcp.request_ua", default=""
)
_request_ip: contextvars.ContextVar[str] = contextvars.ContextVar(
    "x402watch.mcp.request_ip", default=""
)


def get_request_ua() -> str:
    return _request_ua.get()


def get_request_ip() -> str:
    return _request_ip.get()


# ─── Header parsing ──────────────────────────────────────────────────
def _decode(b: bytes) -> str:
    # latin-1 round-trips arbitrary bytes safely; we only display these
    # values in alerts and write them to stats.jsonl, so we don't need
    # strict UTF-8.
    return b.decode("latin-1", errors="replace")


def _client_ip_from_scope(scope: dict) -> str:
    """Prefer the proxy-set headers (CF, X-Forwarded-For, X-Real-IP)
    before falling back to scope['client']. Matches the precedence
    used by app/api.py's `_client_ip()` so alerts on the HTTP API and
    the MCP layer report the same IP for a given caller."""
    headers: Iterable[tuple[bytes, bytes]] = scope.get("headers") or ()
    cf, xff, xri = "", "", ""
    for name, value in headers:
        lower = name.lower()
        if lower == b"cf-connecting-ip" and not cf:
            cf = _decode(value).strip()
        elif lower == b"x-forwarded-for" and not xff:
            xff = _decode(value).split(",")[0].strip()
        elif lower == b"x-real-ip" and not xri:
            xri = _decode(value).strip()
    if cf:
        return cf
    if xff:
        return xff
    if xri:
        return xri
    client = scope.get("client")
    if client and isinstance(client, (list, tuple)) and client:
        return str(client[0])
    return ""


def _user_agent_from_scope(scope: dict) -> str:
    for name, value in scope.get("headers") or ():
        if name.lower() == b"user-agent":
            return _decode(value)
    return ""


# ─── ASGI middleware ─────────────────────────────────────────────────
class MCPRequestContextMiddleware:
    """Wraps FastMCP's HTTP ASGI app. On every HTTP request, populates
    `_request_ua` and `_request_ip` contextvars for the duration of
    the request; resets them on the way out so no inter-request leak.
    Non-HTTP scopes (lifespan, websocket) pass through untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        ua = _user_agent_from_scope(scope)
        ip = _client_ip_from_scope(scope)

        ua_token = _request_ua.set(ua)
        ip_token = _request_ip.set(ip)
        try:
            await self.app(scope, receive, send)
        finally:
            # Reset so the next request on the same task doesn't see
            # the previous request's UA/IP (uvicorn reuses tasks).
            _request_ua.reset(ua_token)
            _request_ip.reset(ip_token)


__all__ = [
    "MCPRequestContextMiddleware",
    "get_request_ua",
    "get_request_ip",
]
