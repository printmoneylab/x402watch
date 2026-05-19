"""
Snippets Moa pastes into the existing Oracle files to wire up the
notification + payment-guidance modules. Each block is self-contained
and idempotent; nothing here imports anything you don't already have
plus the new modules in oracle-patches/x402watch-alerts/.

This is NOT meant to be executed. Treat it as a reference card.
"""

# ─────────────────────────────────────────────────────────────────────
# A. stats.jsonl emission (works in BOTH api.py and mcp_server.py)
# Drop this helper into wherever both files can import from. Pick a
# location that doesn't introduce new circular imports — `app/_stats.py`
# is a safe default.
# ─────────────────────────────────────────────────────────────────────

# app/_stats.py — NEW FILE
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
PATH = Path(os.environ.get('X402WATCH_STATS_PATH', '/home/ubuntu/x402watch/var/stats.jsonl'))
PATH.parent.mkdir(parents=True, exist_ok=True)

def write(record: dict) -> None:
    record.setdefault('ts', datetime.now(KST).isoformat())
    try:
        with PATH.open('a') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\\n')
    except Exception:
        # Stats writes must never break the request path.
        pass
"""


# ─────────────────────────────────────────────────────────────────────
# B. MCP tool wireup (app/mcp_server.py)
# ─────────────────────────────────────────────────────────────────────

WIRE_MCP_HEADER = """
# top of mcp_server.py — additions only, do not remove existing imports
from app.client_classifier import classify, promote_to_suspect
from app.telegram_notify import notify_mcp_tool, notify_unknown_client, notify_burst_suspect
from app._stats import write as _stats_write
"""

WIRE_MCP_TOOL_HOOK = """
# Inside every @mcp.tool function, at the top, BEFORE doing any work:
async def _record_mcp_call(ctx, tool_name: str, *, is_paid_tool: bool):
    ua = ctx.request_context.request.headers.get('user-agent', '') if ctx else ''
    ip = ctx.request_context.request.headers.get('x-forwarded-for', '').split(',')[0].strip() \\
         or (ctx.request_context.request.client.host if ctx and ctx.request_context.request.client else '')
    classification = classify(ua, has_x_payment=False)
    _stats_write({
        'kind': 'mcp_call',
        'tool': tool_name,
        'is_paid_tool': is_paid_tool,
        'ip': ip,
        'ua': ua[:300],
    })
    await notify_mcp_tool(
        tool_name=tool_name,
        classification=classification,
        ip=ip,
        user_agent=ua,
        is_paid_tool=is_paid_tool,
    )
    if classification.tier == 0 and ua:
        await notify_unknown_client(user_agent=ua, ip=ip, tool_name=tool_name)
    return classification

# Then in each tool body:
#   classification = await _record_mcp_call(ctx, 'x402_get_categories', is_paid_tool=False)
"""


# ─────────────────────────────────────────────────────────────────────
# C. Paid HTTP endpoint wireup (app/api.py middle, NOT the last 5 lines)
#
# WARNING: app/api.py last 5 lines are the X402ResourceRewriter wrapper
# from PR #36 v2.2. DO NOT TOUCH that block. Add the snippets below
# alongside the *existing* paid-endpoint handlers, well before the
# `app = X402ResourceRewriter(app)` line.
# ─────────────────────────────────────────────────────────────────────

WIRE_PAYMENT_SUCCESS = """
# After the facilitator has verified payment and the handler is about
# to return a 200 (or whatever the real payload is):
from app.telegram_notify import notify_payment
from app._stats import write as _stats_write

_stats_write({
    'kind': 'payment',
    'endpoint': request.url.path,
    'amount_usd': price_usd,
    'payer': payer_address,
    'ip': client_ip,
    'network': network_label,
})
await notify_payment(
    endpoint=request.url.path,
    price_usd=price_usd,
    network=network_label,
    payer_wallet=payer_address,
    ip=client_ip,
    call_count_24h=...,        # however the existing counter is exposed
    cumulative_calls=...,
    cumulative_usd=...,
    first_seen_date=...,
    is_returning=...,
)
"""

WIRE_POST_SETTLE_FAILURE = """
# Wrap the paid handler's body in try/except and fire this when a 5xx
# happens AFTER the X-PAYMENT header was present (= payment settled but
# we failed to honour it). Suitable for either an exception handler
# (@app.exception_handler) or middleware sitting INSIDE
# X402ResourceRewriter — both work as long as it's not the wrapper.
from app.telegram_notify import notify_post_settle_failure

if response.status_code >= 500 and request.headers.get('x-payment'):
    await notify_post_settle_failure(
        endpoint=request.url.path,
        status=response.status_code,
        ip=client_ip,
        payer_wallet=payer_address,
        tx_hash=tx_hash,
        amount_usd=price_usd,
    )
"""


# ─────────────────────────────────────────────────────────────────────
# D. Paid MCP tool 402 response wireup (app/mcp_server.py)
# ─────────────────────────────────────────────────────────────────────

WIRE_PAID_TOOL_402 = """
# In the helper that wraps the paid HTTP call (e.g. _call_paid_api):
from app.mcp_payment_hint import payment_required_response

async def _call_paid_api(method, endpoint, price_usd, **kw):
    # ... existing logic that may issue the upstream request ...
    if upstream_status == 402:
        return payment_required_response(
            endpoint=endpoint,
            price_usd=price_usd,
            method=method,
        )
    # ... return successful payload on 200 ...
"""


# ─────────────────────────────────────────────────────────────────────
# E. Daily 09:00 KST cron (existing daily summary code)
# ─────────────────────────────────────────────────────────────────────

WIRE_DAILY_SUMMARY = """
# Replace whatever currently sends the daily Telegram digest with:
from app.daily_summary import emit_daily_summary
await emit_daily_summary()
# Or, if the existing daily report builds its own text, append our
# rollup to it instead of replacing:
from app.daily_summary import read_24h_events, rollup, build_daily_text
roll = rollup(read_24h_events())
existing_text += '\\n\\n' + build_daily_text(roll)
"""


# ─────────────────────────────────────────────────────────────────────
# F. Paid tool docstring template (apply to PAID tools ONLY)
# ─────────────────────────────────────────────────────────────────────

PAID_TOOL_EXAMPLE = """
# BEFORE:
@mcp.tool
async def x402_check_wash(buyer: str, seller: str):
    \"\"\"On-demand wash check for an arbitrary buyer/seller pair.\"\"\"
    ...

# AFTER (paid tool — embed the price block + advantage):
from app.mcp_payment_hint import render_paid_docstring

@mcp.tool
async def x402_check_wash(buyer: str, seller: str):
    \"\"\"On-demand wash-filter evaluation of an arbitrary (buyer, seller) pair.

    💰 Price: $0.050 USDC per call
    💳 Payment: x402 micropayment on Base or Solana
    🔧 Client: AgentCash, Pay.sh, or any x402 SDK
    📖 Docs: https://api.x402.printmoneylab.com/.well-known/x402

    🎯 x402watch advantage: Wash-filtered intelligence layer. 4-layer algorithm
       reduces false positives. Open methodology + dispute system.

    Returns label + confidence + signal-by-signal reason.
    \"\"\"
    ...
"""


# ─────────────────────────────────────────────────────────────────────
# G. Free tool docstring marker (apply to FREE tools — one line only)
# ─────────────────────────────────────────────────────────────────────

FREE_TOOL_EXAMPLE = """
@mcp.tool
async def x402_get_categories():
    \"\"\"Get 33 x402 ecosystem categories with wash filtering applied.

    Returns:
      Category list with real_volume_pct, wash_pct, top services.

    Free tier. No payment required. Returns wash-filtered data using the
    same v2.0 algorithm as the paid endpoints.
    \"\"\"
    ...
"""
