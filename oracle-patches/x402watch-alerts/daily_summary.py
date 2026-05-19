"""
Daily 09:00 KST summary builder for x402watch.

Permanent location on Oracle: /home/ubuntu/x402watch/app/daily_summary.py

Wire it into the existing daily cron (whichever module currently emits
the KST 09:00 owner-report Telegram message). The two extension points
are `read_24h_events()` and `build_daily_text()` — feed the function
your existing stats source (stats.jsonl, sqlite, or whatever the
current implementation uses) and it returns the formatted message.

The MCP-tier rollup is the new piece; the merchant / dispute lines
should match what's already being sent so the digest stays unified.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Optional

from app.client_classifier import classify, Classification
from app.telegram_notify import send_text

log = logging.getLogger("daily_summary")

KST = timezone(timedelta(hours=9))
DEFAULT_STATS_PATH = Path(os.environ.get(
    "X402WATCH_STATS_PATH", "/home/ubuntu/x402watch/var/stats.jsonl"
))


# ─── Event ingestion ─────────────────────────────────────────────────
# Expected stats.jsonl record shape (extend in mcp_server.py / api.py
# when emitting). Anything missing is tolerated.
#
#   {"ts": "2026-05-17T13:42:11+09:00",
#    "kind": "mcp_call",                # mcp_call | payment | post_settle | error
#    "tool": "x402_get_categories",
#    "is_paid_tool": false,
#    "ip": "...",
#    "ua": "...",
#    "endpoint": "/api/v1/...",
#    "status": 200,
#    "amount_usd": null,
#    "payer": null}

def read_24h_events(stats_path: Path = DEFAULT_STATS_PATH) -> list[dict]:
    if not stats_path.exists():
        log.warning("stats file missing: %s", stats_path)
        return []
    cutoff = datetime.now(KST) - timedelta(hours=24)
    out: list[dict] = []
    with stats_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts = row.get("ts")
            if not ts:
                continue
            try:
                event_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                continue
            if event_ts.tzinfo is None:
                event_ts = event_ts.replace(tzinfo=timezone.utc)
            if event_ts >= cutoff:
                out.append(row)
    return out


# ─── Rollup ──────────────────────────────────────────────────────────
def rollup(events: Iterable[dict]) -> dict:
    payments = []
    mcp_calls = []
    post_settle_fails = []
    errors_5xx = []
    tier_counter: Counter[int] = Counter()
    tool_counter: Counter[str] = Counter()
    paid_tool_counter: Counter[str] = Counter()
    unique_ips: set[str] = set()
    new_clients: list[tuple[str, str]] = []  # (UA, ip)

    seen_uas: set[str] = set()  # for this 24h window; not persistent

    for ev in events:
        kind = ev.get("kind")
        ip = ev.get("ip") or ""
        ua = ev.get("ua") or ""
        if ip:
            unique_ips.add(ip)

        if kind == "payment":
            payments.append(ev)
            continue
        if kind == "post_settle_fail":
            post_settle_fails.append(ev)
            continue
        if kind == "error" and 500 <= int(ev.get("status") or 0) < 600:
            errors_5xx.append(ev)
            continue

        if kind == "mcp_call":
            tool = ev.get("tool") or "?"
            mcp_calls.append(ev)
            tool_counter[tool] += 1
            if ev.get("is_paid_tool"):
                paid_tool_counter[tool] += 1
            c: Classification = classify(ua, has_x_payment=bool(ev.get("payer")))
            tier_counter[c.tier] += 1
            if c.tier == 0 and ua and ua not in seen_uas:
                seen_uas.add(ua)
                new_clients.append((ua, ip))

    total_paid_usd = sum(float(p.get("amount_usd") or 0) for p in payments)

    return {
        "payments": payments,
        "payment_total_usd": round(total_paid_usd, 4),
        "mcp_total": len(mcp_calls),
        "post_settle_fails": post_settle_fails,
        "errors_5xx": errors_5xx,
        "tier_counts": dict(sorted(tier_counter.items())),
        "top_tools": tool_counter.most_common(3),
        "paid_tool_counts": dict(paid_tool_counter),
        "unique_ips": len(unique_ips),
        "new_clients": new_clients[:5],
    }


# ─── Formatting ──────────────────────────────────────────────────────
TIER_LABEL = {
    1: "💎 paid",
    2: "🔵 AI client",
    3: "🟡 agent framework",
    4: "⚪ directory bot",
    5: "⚪ generic HTTP",
    6: "🔴 suspect",
    0: "❓ unknown UA",
}


def build_daily_text(roll: dict, *, when: Optional[datetime] = None) -> str:
    when = when or datetime.now(KST)
    lines = [
        f"📊 x402watch daily — {when.strftime('%Y-%m-%d %H:%M KST')}",
        "",
        f"💰 Payments: {len(roll['payments'])} / ${roll['payment_total_usd']:.4f}",
    ]
    if roll["post_settle_fails"]:
        lines.append(f"🚨 Post-settle failures: {len(roll['post_settle_fails'])}")
    if roll["errors_5xx"]:
        lines.append(f"⚠️  5xx errors: {len(roll['errors_5xx'])}")

    lines.append("")
    lines.append(f"🛰  MCP calls: {roll['mcp_total']}   unique IPs: {roll['unique_ips']}")

    if roll["tier_counts"]:
        lines.append("   tier breakdown:")
        for tier, count in roll["tier_counts"].items():
            lines.append(f"     {TIER_LABEL.get(tier, str(tier))}: {count}")

    if roll["top_tools"]:
        lines.append("   top tools:")
        for tool, n in roll["top_tools"]:
            mark = " 💰" if tool in roll["paid_tool_counts"] else ""
            lines.append(f"     {tool}{mark}: {n}")

    if roll["new_clients"]:
        lines.append("")
        lines.append("❓ New clients (first seen in last 24h):")
        for ua, ip in roll["new_clients"]:
            lines.append(f"   {ua[:80]}  ({ip})")

    return "\n".join(lines)


# ─── Driver (called from existing daily cron) ────────────────────────
async def emit_daily_summary(stats_path: Path = DEFAULT_STATS_PATH) -> None:
    events = read_24h_events(stats_path)
    roll = rollup(events)
    text = build_daily_text(roll)
    await send_text(text, kind="daily_summary")
    log.info("daily summary sent: payments=%d mcp=%d 5xx=%d",
             len(roll["payments"]), roll["mcp_total"], len(roll["errors_5xx"]))


__all__ = ["read_24h_events", "rollup", "build_daily_text", "emit_daily_summary"]
