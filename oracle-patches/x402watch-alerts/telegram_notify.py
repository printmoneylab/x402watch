"""
Telegram alert helpers for x402watch — payment / MCP-tool / post-settle
formatting + dedupe + IP enrichment.

Permanent location on Oracle: /home/ubuntu/x402watch/app/telegram_notify.py

Design notes
============
- Everything is async-safe and never raises into the request path: if
  Telegram is down or the env vars aren't set, we log and move on.
- Dedupe uses an in-process TTL cache keyed by (kind, dedupe_key). We
  intentionally don't reach for Redis here — the alert layer is supposed
  to be cheap and self-contained; if multi-worker dedupe becomes a
  problem later it's a 5-line swap.
- IP enrichment hits ipinfo.io with a 24h LRU cache. A missing
  IPINFO_TOKEN env var degrades gracefully (no enrichment, just the IP).
- Formatting follows the KR Crypto pattern Moa already validated: 10
  fields on the payment alert, an MCP-tool alert that reads correctly
  for both ad-hoc humans and the 09:00 KST digest, and a dedicated
  post-settle-failure alert that flags 5xx-after-X-PAYMENT.

Public API
==========
  await notify_payment(...)
  await notify_mcp_tool(...)
  await notify_post_settle_failure(...)
  await notify_unknown_client(...)
  await notify_burst_suspect(...)
  await send_text(text, *, dedupe_key=None, ttl=300)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from app.client_classifier import Classification

log = logging.getLogger("telegram_notify")

KST = timezone(timedelta(hours=9))
DEFAULT_DEDUPE_TTL = 300  # 5 min
IPINFO_CACHE_TTL = 86400  # 24 h


# ─── Low-level send ──────────────────────────────────────────────────
_dedupe_cache: dict[tuple[str, str], float] = {}


def _dedupe_should_send(kind: str, key: Optional[str], ttl: int) -> bool:
    if not key:
        return True
    now = time.time()
    # Garbage-collect occasionally to keep the dict bounded.
    if len(_dedupe_cache) > 4096:
        cutoff = now - max(ttl, DEFAULT_DEDUPE_TTL)
        for k, t in list(_dedupe_cache.items()):
            if t < cutoff:
                _dedupe_cache.pop(k, None)
    last = _dedupe_cache.get((kind, key))
    if last and now - last < ttl:
        return False
    _dedupe_cache[(kind, key)] = now
    return True


async def send_text(
    text: str,
    *,
    kind: str = "generic",
    dedupe_key: Optional[str] = None,
    ttl: int = DEFAULT_DEDUPE_TTL,
) -> None:
    """Fire-and-forget Telegram message. Honors the dedupe TTL. Never raises."""
    if not _dedupe_should_send(kind, dedupe_key, ttl):
        log.debug("telegram dedupe hit: kind=%s key=%s", kind, dedupe_key)
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        log.warning("telegram env not configured — skipping %s alert", kind)
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
            )
            if r.status_code >= 400:
                log.error("telegram non-200: %s %s", r.status_code, r.text[:200])
    except Exception:
        log.exception("telegram send failed (kind=%s)", kind)


# ─── IP enrichment ───────────────────────────────────────────────────
_ipinfo_cache: dict[str, tuple[float, dict]] = {}


async def _ipinfo(ip: str) -> dict:
    """Returns a small dict: city, country, org, datacenter (bool)."""
    if not ip or ip in ("127.0.0.1", "::1"):
        return {"city": "local", "country": "", "org": "loopback", "datacenter": False}
    now = time.time()
    cached = _ipinfo_cache.get(ip)
    if cached and now - cached[0] < IPINFO_CACHE_TTL:
        return cached[1]
    token = os.environ.get("IPINFO_TOKEN", "")
    url = f"https://ipinfo.io/{ip}/json" + (f"?token={token}" if token else "")
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(url)
            data = r.json() if r.status_code == 200 else {}
    except Exception:
        log.exception("ipinfo lookup failed for %s", ip)
        data = {}
    out = {
        "city": data.get("city") or "?",
        "country": data.get("country") or "?",
        "org": (data.get("org") or "")[:80],
        "datacenter": _looks_like_datacenter(data.get("org") or ""),
    }
    _ipinfo_cache[ip] = (now, out)
    return out


_DC_HINTS = (
    "amazon", "aws", "google", "gcp", "microsoft", "azure", "linode",
    "digitalocean", "hetzner", "ovh", "oracle", "fastly", "cloudflare",
    "vultr", "scaleway", "alibaba", "tencent",
)


def _looks_like_datacenter(org: str) -> bool:
    o = org.lower()
    return any(h in o for h in _DC_HINTS)


def _network_label(network: str) -> str:
    n = network.lower()
    if "8453" in n or "base" in n:
        return "Base"
    if "solana" in n:
        return "Solana"
    if "polygon" in n or "137" in n:
        return "Polygon"
    if "arbitrum" in n:
        return "Arbitrum"
    return network


def _now_kst() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")


# ─── Payment success alert (10 fields, KR Crypto layout) ─────────────
# Caller is responsible for keeping the cumulative counters (call_count,
# total_usd, first_seen_date, is_returning). Those typically live in a
# small JSONL or sqlite next to the API, scoped per buyer wallet.
async def notify_payment(
    *,
    endpoint: str,
    price_usd: float,
    network: str,
    payer_wallet: str,
    ip: str,
    call_count_24h: int,
    cumulative_calls: int,
    cumulative_usd: float,
    first_seen_date: str,
    is_returning: bool,
) -> None:
    info = await _ipinfo(ip)
    dc = " 🏢 datacenter" if info["datacenter"] else ""
    user_state = "🔁 누적 사용자" if is_returning else "🆕 신규 사용자"
    text = (
        "💰 유료 결제 성공!\n"
        f"엔드포인트: {endpoint}\n"
        f"가격: ${price_usd:.3f}\n"
        f"네트워크: {_network_label(network)}\n"
        f"지갑: {payer_wallet[:6]}…{payer_wallet[-4:]}\n"
        f"IP: {ip}{dc} ({info['city']}, {info['country']})\n"
        f"사용자: {user_state}\n"
        f"누적: {cumulative_calls}건 / ${cumulative_usd:.4f}\n"
        f"첫 결제: {first_seen_date}\n"
        f"시간: {_now_kst()}"
    )
    # Each successful payment is worth surfacing — no dedupe.
    await send_text(text, kind="payment")


# ─── MCP tool-call alert (tier-aware) ────────────────────────────────
async def notify_mcp_tool(
    *,
    tool_name: str,
    classification: Classification,
    ip: str,
    user_agent: str,
    is_paid_tool: bool,
    args_summary: Optional[str] = None,
) -> None:
    """Emit a tier-appropriate Telegram alert for an MCP tool call.

    Tier 4/5 are routed to the daily digest only (no immediate alert) —
    we just record them via the dedupe cache so the daily summary code
    can pick them up. Tier 1/2/3/6 fire immediately.
    """
    # Tier 4/5: daily-only — caller should write to stats.jsonl, this
    # function is a no-op for them so we don't drown the chat.
    if classification.action == "daily":
        return

    info = await _ipinfo(ip)
    dc = " 🏢 dc" if info["datacenter"] else ""
    paid_marker = " 💰 paid" if is_paid_tool else " (free tool)"

    head = f"{classification.emoji} MCP call · Tier {classification.tier} · {classification.label}"
    body = [
        head,
        f"tool: {tool_name}{paid_marker}",
        f"ip: {ip}{dc} ({info['city']}, {info['country']})",
        f"UA: {user_agent[:120]}",
    ]
    if args_summary:
        body.append(f"args: {args_summary[:200]}")
    body.append(f"시간: {_now_kst()}")
    text = "\n".join(body)

    # Dedupe: 5 min, keyed by (tool, ip) so the same caller hammering
    # the same tool gets one alert per 5 min window instead of N.
    dedupe_key = f"{tool_name}|{ip}"
    ttl = DEFAULT_DEDUPE_TTL
    if classification.action == "first_only":
        # First-time unknown UA gets one alert per UA per 24h.
        dedupe_key = f"unknown:{user_agent}"
        ttl = 86400
    await send_text(text, kind="mcp_tool", dedupe_key=dedupe_key, ttl=ttl)


# ─── Post-settle failure alert (5xx after X-PAYMENT) ─────────────────
async def notify_post_settle_failure(
    *,
    endpoint: str,
    status: int,
    ip: str,
    payer_wallet: Optional[str],
    tx_hash: Optional[str],
    amount_usd: Optional[float],
) -> None:
    """Caller invokes this when a paid endpoint returns 5xx but the
    request carried an X-PAYMENT header — strong signal that we settled
    a payment and then failed to honour it. 5-min dedupe per endpoint
    so we don't spam during an outage."""
    text = (
        "🚨 SETTLE 후 응답 실패 의심\n"
        f"endpoint: {endpoint}\n"
        f"status: {status}\n"
        f"ip: {ip}\n"
        f"payer: {payer_wallet or '?'}\n"
        f"tx_hash: {tx_hash or '?'}\n"
        f"amount: ${amount_usd:.3f}" if amount_usd is not None else f"amount: ?"
    )
    dedupe_key = f"{endpoint}|{status}"
    await send_text(text, kind="post_settle", dedupe_key=dedupe_key, ttl=DEFAULT_DEDUPE_TTL)


# ─── Unknown client first-seen alert ─────────────────────────────────
async def notify_unknown_client(
    *,
    user_agent: str,
    ip: str,
    tool_name: Optional[str] = None,
) -> None:
    info = await _ipinfo(ip)
    text = (
        "❓ Unknown client first seen\n"
        f"UA: {user_agent[:200]}\n"
        f"ip: {ip} ({info['city']}, {info['country']}, org={info['org']})\n"
        + (f"first tool: {tool_name}\n" if tool_name else "")
        + f"시간: {_now_kst()}"
    )
    await send_text(text, kind="unknown_client",
                    dedupe_key=f"ua:{user_agent}", ttl=86400)


# ─── Burst suspect alert ─────────────────────────────────────────────
async def notify_burst_suspect(
    *,
    user_agent: str,
    ip: str,
    requests_in_window: int,
    window_seconds: int,
) -> None:
    text = (
        "🔴 SUSPECT burst — rate limiting recommended\n"
        f"UA: {user_agent[:120]}\n"
        f"ip: {ip}\n"
        f"hits: {requests_in_window} in {window_seconds}s\n"
        f"시간: {_now_kst()}"
    )
    await send_text(text, kind="burst", dedupe_key=f"burst:{ip}", ttl=3600)


__all__ = [
    "send_text",
    "notify_payment",
    "notify_mcp_tool",
    "notify_post_settle_failure",
    "notify_unknown_client",
    "notify_burst_suspect",
]
