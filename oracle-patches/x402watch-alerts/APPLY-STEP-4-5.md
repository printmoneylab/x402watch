# Steps 4 + 5 — exact edits for app/api.py and app/mcp_server.py

Decision recap: **Option A.1 (safe additive)**. The existing
`payment_notify_middleware` at api.py:1951 and its `_enrich_and_notify`
inner task are kept intact. We add three small things alongside them:

  1. one new import (`_stats.write` for jsonl logging consumed by
     `daily_summary.py`),
  2. a `stats.jsonl` write inside `_enrich_and_notify`,
  3. a post-settle-failure branch inside `payment_notify_middleware`.

mcp_server.py is touched in five places: imports, a new
`_record_mcp_call` helper, and one tweak per tool (Context arg + call
the helper + `FREE_TOOL_TAGLINE` in the docstring).

Every change has an anchor line shown verbatim from your paste so the
edits are mechanical. Apply with `$EDITOR` or `sed -i`. After each
file, run `venv/bin/python scripts/verify_wireup.py` (committed earlier
as `oracle-patches/x402watch-alerts/verify_wireup.py` — copy to
`/home/ubuntu/x402watch/scripts/` first).

**DO NOT TOUCH** in either file:
- api.py last 5 lines (the `app = X402ResourceRewriter(app)` block).
- app/x402_meta.py at all.

---

## File 1 — `app/api.py` (3 edits)

### Edit 1 — add one import line

**Anchor** (around line 1750, in the Day-21 telegram block):

```python
import httpx as _httpx_tg
from fastapi import Request as _Request_tg
```

**Insert immediately after these two lines:**

```python
from app._stats import write as _stats_write
from app.telegram_notify import notify_post_settle_failure
```

That's the entire Step-4 import surface — `_stats_write` for the jsonl
record, `notify_post_settle_failure` for the new branch in edit 3.

### Edit 2 — write to stats.jsonl on every successful paid call

**Anchor** (around line 1982, inside `_enrich_and_notify`, RIGHT AFTER
the existing `stats = await _record_payment_stats(...)` line):

```python
            stats = await _record_payment_stats(redis_client, ip, amount)
```

**Insert immediately after that line (matching indentation — 12 spaces):**

```python
            # Step 6: also emit a structured event for daily_summary.py.
            # Never raises; _stats_write swallows IO errors itself.
            _stats_write({
                "kind": "payment",
                "endpoint": endpoint_label,
                "amount_usd": float(amount),
                "ip": ip,
                "is_paid_tool": True,
            })
```

This runs inside the existing background task so it adds no latency to
the user response. Owner-IP traffic short-circuits *before* this block
(line 1974 `if ip in _OWNER_IPS: ... return`), so owner test calls do
not bloat the summary file.

### Edit 3 — post-settle failure detection

**Anchor** (around line 1953, the early-return inside
`payment_notify_middleware` that the inner-task hook is wrapped around):

```python
@app.middleware("http")
async def payment_notify_middleware(request: _Request_tg, call_next):
    response = await call_next(request)
    matched = _match_paid(request.url.path, request.method)
    if matched is None or response.status_code != 200:
        return response
```

**Replace the `if matched is None or response.status_code != 200:`
block with:**

```python
@app.middleware("http")
async def payment_notify_middleware(request: _Request_tg, call_next):
    response = await call_next(request)
    matched = _match_paid(request.url.path, request.method)

    # Step 6: post-settle failure — 5xx on a paid path where the client
    # supplied X-PAYMENT. Strong signal that we settled then failed to
    # honour. Fire-and-forget; 5-min dedupe lives in notify_telegram.
    if (
        matched is not None
        and 500 <= response.status_code < 600
        and request.headers.get("x-payment")
    ):
        endpoint_label_ps, amount_ps = matched
        ip_ps = _client_ip(request)
        _stats_write({
            "kind": "post_settle_fail",
            "endpoint": endpoint_label_ps,
            "status": response.status_code,
            "ip": ip_ps,
            "amount_usd": float(amount_ps),
        })
        _asyncio_tg.create_task(notify_post_settle_failure(
            endpoint=endpoint_label_ps,
            status=response.status_code,
            ip=ip_ps,
            payer_wallet=None,  # not available without decoding X-PAYMENT
            tx_hash=None,
            amount_usd=float(amount_ps),
        ))

    if matched is None or response.status_code != 200:
        return response
```

Only one line of the original survives unchanged (the `if matched is
None or response.status_code != 200: return response` early-return);
everything else above it is added.

### Edit 4 (optional — daily 09:00 KST summary)

The visible portion of api.py has no daily summary cron. Cleanest path
is a separate systemd unit pair (no api.py edit). Create on Oracle:

`/etc/systemd/system/x402watch-daily.service`:

```ini
[Unit]
Description=x402watch daily KST 09:00 summary
After=network.target x402watch-api.service

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/home/ubuntu/x402watch
EnvironmentFile=/home/ubuntu/x402watch/.env
ExecStart=/home/ubuntu/x402watch/venv/bin/python -c "import asyncio; from app.daily_summary import emit_daily_summary; asyncio.run(emit_daily_summary())"
```

`/etc/systemd/system/x402watch-daily.timer`:

```ini
[Unit]
Description=Run x402watch daily summary at 09:00 KST

[Timer]
OnCalendar=*-*-* 00:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

Enable + verify:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now x402watch-daily.timer
systemctl list-timers x402watch-daily.timer
sudo systemctl start x402watch-daily.service   # one-shot test
sudo journalctl -u x402watch-daily.service -n 20 --no-pager
```

Note: `OnCalendar=*-*-* 00:00:00 UTC` = 09:00 KST daily. The first
manual `start` will fire immediately so you can confirm the Telegram
message arrives before the timer takes over.

---

## File 2 — `app/mcp_server.py` (5 edits)

### Edit 1 — header imports

**Anchor** (lines 25-28 in your paste):

```python
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field
```

**Replace with:**

```python
import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP, Context
from pydantic import Field

from app.client_classifier import classify
from app.telegram_notify import notify_mcp_tool, notify_unknown_client
from app._stats import write as _stats_write
from app.mcp_payment_hint import FREE_TOOL_TAGLINE
```

Three lines added, one line (the `fastmcp` import) extended with
`Context`. Context is what FastMCP uses to expose the underlying
Starlette `Request` to tools — schema-invisible to MCP clients, so
adding it to a tool signature does NOT change the public tool shape.

### Edit 2 — `_record_mcp_call` helper

**Anchor** (lines 70-78 in your paste — the existing `_track` function):

```python
def _track(tool_name: str) -> None:
    now = time.monotonic()
    last = _last_notified.get(tool_name, 0)
    if now - last < _NOTIFY_COOLDOWN_SECONDS:
        return
    _last_notified[tool_name] = now
    asyncio.create_task(_tg_notify(f"x402watch MCP: {tool_name}"))
```

**Insert IMMEDIATELY AFTER the `_track` function (before `async def
_get(...)`):**

```python
def _extract_request_meta(ctx: Context | None) -> tuple[str, str]:
    """Best-effort (user_agent, ip) extraction from FastMCP Context.
    Returns ('', '') if anything goes wrong — downstream alert code
    handles empty UA gracefully (Tier 0 unknown, no immediate notify)."""
    try:
        req = getattr(getattr(ctx, "request_context", None), "request", None)
        if req is None:
            return "", ""
        ua = req.headers.get("user-agent", "") or ""
        ip = (
            req.headers.get("cf-connecting-ip", "").strip()
            or req.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or req.headers.get("x-real-ip", "").strip()
            or (req.client.host if req.client else "")
        )
        return ua[:300], ip or ""
    except Exception:
        return "", ""


def _record_mcp_call(tool_name: str, ctx: Context | None) -> None:
    """Tier-aware MCP-call recorder. Runs alongside the legacy _track
    notification — see APPLY-STEP-4-5.md option A.1 rationale."""
    ua, ip = _extract_request_meta(ctx)
    classification = classify(ua, has_x_payment=False)

    _stats_write({
        "kind": "mcp_call",
        "tool": tool_name,
        "is_paid_tool": False,           # all x402watch MCP tools are free
        "ip": ip,
        "ua": ua,
        "tier": classification.tier,
        "tier_label": classification.label,
    })

    if classification.action == "immediate":
        asyncio.create_task(notify_mcp_tool(
            tool_name=tool_name,
            classification=classification,
            ip=ip,
            user_agent=ua,
            is_paid_tool=False,
        ))
    elif classification.action == "first_only" and ua:
        asyncio.create_task(notify_unknown_client(
            user_agent=ua, ip=ip, tool_name=tool_name,
        ))
```

The helper is *additive*. Existing `_track(tool_name)` keeps doing the
legacy `x402watch MCP: {tool_name}` Telegram ping; the new
`_record_mcp_call(tool_name, ctx)` fires the tier-aware alerts on top.

### Edits 3-7 — each of the 5 tools

For each tool: (a) add `ctx: Context = None` as the last parameter,
(b) add the `_record_mcp_call(...)` call right after the existing
`_track(...)`, (c) append `FREE_TOOL_TAGLINE` to the docstring.

The `= None` default keeps the signature backwards-compatible if a
client somehow bypasses FastMCP's Context injection.

#### Tool 1 — `x402_get_categories` (lines 93-101)

**Replace:**

```python
@mcp.tool()
async def x402_get_categories() -> dict:
    """List all 33 x402 service categories with aggregate stats: services
    count, 24h volume, transaction count, real-volume %, and label
    distribution. Use this to understand the shape of the x402 ecosystem
    before drilling into specific services or wallets.
    """
    _track("x402_get_categories")
    return await _get("/api/v1/categories")
```

**With:**

```python
@mcp.tool()
async def x402_get_categories(ctx: Context = None) -> dict:
    """List all 33 x402 service categories with aggregate stats: services
    count, 24h volume, transaction count, real-volume %, and label
    distribution. Use this to understand the shape of the x402 ecosystem
    before drilling into specific services or wallets.

    """ + FREE_TOOL_TAGLINE
    _track("x402_get_categories")
    _record_mcp_call("x402_get_categories", ctx)
    return await _get("/api/v1/categories")
```

#### Tool 2 — `x402_get_service` (lines 104-116)

**Replace:**

```python
@mcp.tool()
async def x402_get_service(
    service_id: int = Field(
        description="Numeric x402 service id (visible in /services list and detail URLs)."
    ),
) -> dict:
    """Get the full detail record for one x402 service: name, description,
    seller address, chain, price, 24h and total transaction stats, 30-day
    daily volume time series, buyer-label distribution, and top buyers.
    Use this to evaluate a single service's traffic composition.
    """
    _track("x402_get_service")
    return await _get(f"/api/v1/services/{int(service_id)}")
```

**With:**

```python
@mcp.tool()
async def x402_get_service(
    service_id: int = Field(
        description="Numeric x402 service id (visible in /services list and detail URLs)."
    ),
    ctx: Context = None,
) -> dict:
    """Get the full detail record for one x402 service: name, description,
    seller address, chain, price, 24h and total transaction stats, 30-day
    daily volume time series, buyer-label distribution, and top buyers.
    Use this to evaluate a single service's traffic composition.

    """ + FREE_TOOL_TAGLINE
    _track("x402_get_service")
    _record_mcp_call("x402_get_service", ctx)
    return await _get(f"/api/v1/services/{int(service_id)}")
```

#### Tool 3 — `x402_check_wash` (lines 119-149)

**Replace:**

```python
@mcp.tool()
async def x402_check_wash(
    address: str = Field(
        default="",
        description="Optional wallet or seller address. When provided, the response includes a hint about the paid per-address endpoint.",
    ),
) -> dict:
    """Get the aggregate wash-report dataset: 30-day total active buyers,
    real-volume %, suspected_wash and self_test counts, full 8-label
    distribution, 14-day wash percentage time series, and five anonymized
    case studies (Service A through E) with pattern signals.

    For per-address real-time wash analysis with full signal breakdown,
    use the paid POST /api/v1/wash/check HTTP endpoint ($0.05 USDC) —
    that endpoint speaks x402, agents pay and receive data in a single
    HTTP round-trip.
    """
    _track("x402_check_wash")
    payload = await _get("/api/v1/wash-report")
```

**With:**

```python
@mcp.tool()
async def x402_check_wash(
    address: str = Field(
        default="",
        description="Optional wallet or seller address. When provided, the response includes a hint about the paid per-address endpoint.",
    ),
    ctx: Context = None,
) -> dict:
    """Get the aggregate wash-report dataset: 30-day total active buyers,
    real-volume %, suspected_wash and self_test counts, full 9-label
    distribution, 14-day wash percentage time series, and five anonymized
    case studies (Service A through E) with pattern signals.

    For per-address real-time wash analysis with full signal breakdown,
    use the paid POST /api/v1/wash/check HTTP endpoint ($0.05 USDC) —
    that endpoint speaks x402, agents pay and receive data in a single
    HTTP round-trip.

    """ + FREE_TOOL_TAGLINE
    _track("x402_check_wash")
    _record_mcp_call("x402_check_wash", ctx)
    payload = await _get("/api/v1/wash-report")
```

(also updated `8-label` → `9-label` to match the v2.0 taxonomy.)

#### Tool 4 — `x402_search_services` (lines 152-187)

**Replace the parameter list and docstring/body header — anchor:**

```python
@mcp.tool()
async def x402_search_services(
    search: str = Field(
        default="",
        description="Free-text match against name, description, or seller address.",
    ),
    category: str = Field(
        default="",
        description="Filter to a single category slug (e.g. 'ai_inference', 'wallet_analytics').",
    ),
    chain: str = Field(
        default="",
        description="Filter to one chain: 'base', 'solana', 'arbitrum', 'base-sepolia'.",
    ),
    sort: str = Field(
        default="tx_24h",
        description="Sort key: tx_24h | volume_24h | tx_total | price | real_pct | wash_pct | first_seen | alpha.",
    ),
    page: int = Field(default=1, description="1-indexed page number."),
    page_size: int = Field(
        default=24, description="Page size (max 200; default 24)."
    ),
) -> dict:
    """Search the index of 36k+ x402 services with filters. Returns a
    paginated list of matching services with their stats and label
    mix. Use this to find services by topic, chain, or seller wallet.
    """
    _track("x402_search_services")
```

**With:**

```python
@mcp.tool()
async def x402_search_services(
    search: str = Field(
        default="",
        description="Free-text match against name, description, or seller address.",
    ),
    category: str = Field(
        default="",
        description="Filter to a single category slug (e.g. 'ai_inference', 'wallet_analytics').",
    ),
    chain: str = Field(
        default="",
        description="Filter to one chain: 'base', 'solana', 'arbitrum', 'base-sepolia'.",
    ),
    sort: str = Field(
        default="tx_24h",
        description="Sort key: tx_24h | volume_24h | tx_total | price | real_pct | wash_pct | first_seen | alpha.",
    ),
    page: int = Field(default=1, description="1-indexed page number."),
    page_size: int = Field(
        default=24, description="Page size (max 200; default 24)."
    ),
    ctx: Context = None,
) -> dict:
    """Search the index of 36k+ x402 services with filters. Returns a
    paginated list of matching services with their stats and label
    mix. Use this to find services by topic, chain, or seller wallet.

    """ + FREE_TOOL_TAGLINE
    _track("x402_search_services")
    _record_mcp_call("x402_search_services", ctx)
```

#### Tool 5 — `x402_get_trends` (lines 190-199)

**Replace:**

```python
@mcp.tool()
async def x402_get_trends() -> dict:
    """Get the last-24-hour trends snapshot: new services count vs the
    previous 24h, total transaction count, total USDC volume, active
    buyer count, daily new-services bar (14 days), recent new services
    (top 10), category volume movers, and hot services with traffic
    surges (>= 100 24h tx and >= +50% growth). Refreshed every 5 min.
    """
    _track("x402_get_trends")
    return await _get("/api/v1/trends")
```

**With:**

```python
@mcp.tool()
async def x402_get_trends(ctx: Context = None) -> dict:
    """Get the last-24-hour trends snapshot: new services count vs the
    previous 24h, total transaction count, total USDC volume, active
    buyer count, daily new-services bar (14 days), recent new services
    (top 10), category volume movers, and hot services with traffic
    surges (>= 100 24h tx and >= +50% growth). Refreshed every 5 min.

    """ + FREE_TOOL_TAGLINE
    _track("x402_get_trends")
    _record_mcp_call("x402_get_trends", ctx)
    return await _get("/api/v1/trends")
```

### What about burst detection? (E in the spec)

`notify_burst_suspect` is the public API on `telegram_notify.py`. It
fires when the same UA hits N+ requests in M seconds. Implementing the
counter requires per-UA rate tracking, which fits more naturally in
`_record_mcp_call`. **Defer to Phase 2** — we don't have enough
production traffic on MCP yet to tune the threshold, and the
single-tool 5-min `_track` dedupe already throttles the most common
abuse pattern.

If burst tracking is needed sooner, the right place is a couple of
lines inside `_record_mcp_call` after `classification = classify(...)`:
maintain a `dict[str, deque[float]]` of UA → recent timestamps,
trim to a 1h window, and when `len > 50` call
`notify_burst_suspect(...)` and skip the regular notify.

---

## Apply commands

```bash
ssh ubuntu@168.138.195.65
cd /home/ubuntu/x402watch

# 0. confirm everything from Step 2 is still in place
ls app/api.py.bak.20260519-alerts app/mcp_server.py.bak.20260519-alerts
ls app/client_classifier.py app/telegram_notify.py app/daily_summary.py \
   app/mcp_payment_hint.py app/_stats.py app/paid_tools_catalog.py

# 1. copy the verifier into scripts/
mkdir -p scripts
cp oracle-patches/x402watch-alerts/verify_wireup.py scripts/

# 2. apply api.py edits with $EDITOR (vim/nano).
$EDITOR app/api.py
# - Edit 1: add 2 imports after line ~1751
# - Edit 2: add stats.jsonl write after `stats = await _record_payment_stats(...)` (~line 1982)
# - Edit 3: insert post-settle block before the early-return at ~line 1955

# 3. syntax + wrapper-tail sanity (the verifier checks both)
venv/bin/python scripts/verify_wireup.py
# expect: PASS on api.py syntax + wrapper-last + module imports

# 4. apply mcp_server.py edits with $EDITOR
$EDITOR app/mcp_server.py
# - Edit 1: header imports
# - Edit 2: insert _extract_request_meta + _record_mcp_call after _track
# - Edits 3-7: each of the 5 tools (ctx param, _record_mcp_call, FREE_TOOL_TAGLINE)

# 5. verify again
venv/bin/python scripts/verify_wireup.py

# 6. restart
sudo systemctl restart x402watch-api
sudo systemctl restart x402watch-mcp
sleep 1
sudo journalctl -u x402watch-api -n 30 --no-pager | tail -10
sudo journalctl -u x402watch-mcp -n 30 --no-pager | tail -10
# expect: no ImportError, application startup complete

# 7. (optional) install daily timer per Edit-4 above
```

---

## Verification

### V1 — PR #36 v2.2 still healthy (mandatory pre + post)

```bash
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep -i x-x402-rewriter
# expect: x-x402-rewriter: v2.2

curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(access-control|x-x402-rewriter|vary):"
# expect: ACAO echo, Expose-Headers, Vary: Origin, Rewriter v2.2
```

### V2 — stats.jsonl is being written

```bash
# trigger a free MCP call from any UA
curl -s -H "User-Agent: Cursor/0.40 (verify)" \
  "https://api.x402.printmoneylab.com/api/v1/health"
sleep 1
tail -3 /home/ubuntu/x402watch/var/stats.jsonl
# expect: at least one row from a recent owner-test / smoke (Cursor will
# show up if you actually call an MCP tool from Cursor; plain HTTP to
# the REST API only fires inside payment_notify_middleware on a paid 200)
```

### V3 — daily summary builds

```bash
cd /home/ubuntu/x402watch
venv/bin/python -c "
import asyncio
from app.daily_summary import read_24h_events, rollup, build_daily_text
events = read_24h_events()
roll = rollup(events)
print(build_daily_text(roll))
"
# expect: a formatted '📊 x402watch daily — ...' message with
# Payments + MCP + tier breakdown sections.
```

### V4 — owner-test payment regression (manual)

Run one owner-test x402 paid call on Base and one on Solana. Expect:

- HTTP 200 with the actual paid payload.
- Existing Korean Telegram alert ("🛠️ x402watch owner test — ...") still fires.
- New row in `var/stats.jsonl` with `kind=payment`.

### V5 — non-owner paid call (manual)

If you have a non-owner test wallet, fire one $0.005 wash-detail call.
Expect:

- HTTP 200 with payload.
- Existing rich Korean payment alert fires.
- Same `var/stats.jsonl` row but from a real IP.

### V6 — post-settle simulation (manual, optional)

This is harder to simulate without breaking something — easier to wait
for a real 5xx. To force one for the test, you could briefly stop the
DB pool, but that's invasive. **Recommended**: skip this verification
and let the first real 5xx prove it.

---

## Expected alert shapes (after deploy)

### Tier-2 MCP call (existing legacy alert + new tier-aware alert)

Legacy `_track` (unchanged):
```
x402watch MCP: x402_get_categories
```

New tier-aware (from `_record_mcp_call` → `notify_mcp_tool`):
```
🔵 MCP call · Tier 2 · Cursor IDE
tool: x402_get_categories (free tool)
ip: 34.126.79.53 🏢 dc (Singapore, SG)
UA: Cursor/0.40.2 (linux)
시간: 2026-05-19 22:38:09
```

### Tier-4 MCP call

Legacy fires; tier-aware does NOT (`action == "daily"`, routes to the
daily digest instead of Telegram chat). Net effect: directory bots
keep producing the same one Telegram line they did before, you just
also get a daily roll-up.

### Tier-0 (unknown UA) first seen

Legacy fires; tier-aware adds:
```
❓ Unknown client first seen
UA: Mozilla/5.0 (some new tool)
ip: ... (Seoul, KR, org=KT)
first tool: x402_search_services
시간: 2026-05-19 22:38:09
```

(once per UA per 24h)

### Payment success (unchanged from before — still the existing
Korean rich format). New behaviour: a `stats.jsonl` line is appended
in the same moment.

### Post-settle failure (new — fires only on 5xx + X-PAYMENT)

```
🚨 SETTLE 후 응답 실패 의심
endpoint: /api/v1/services/{id}/wash-detail
status: 503
ip: 1.249.16.154
payer: ?
tx_hash: ?
amount: $0.005
```

5-min dedupe per (endpoint, status).

### Daily 09:00 KST summary (new)

```
📊 x402watch daily — 2026-05-20 09:00 KST

💰 Payments: 7 / $0.0350

🛰  MCP calls: 142   unique IPs: 23
   tier breakdown:
     🔵 AI client: 18
     🟡 agent framework: 4
     ⚪ directory bot: 87
     ⚪ generic HTTP: 26
     ❓ unknown UA: 7
   top tools:
     x402_get_categories: 61
     x402_search_services: 33
     x402_get_trends: 22

❓ New clients (first seen in last 24h):
   Some unfamiliar agent UA  (1.2.3.4)
```

---

## Rollback (< 1 min per file)

```bash
cd /home/ubuntu/x402watch
cp app/api.py.bak.20260519-alerts app/api.py
cp app/mcp_server.py.bak.20260519-alerts app/mcp_server.py
sudo systemctl restart x402watch-api
sudo systemctl restart x402watch-mcp
# X402ResourceRewriter wrapper is untouched in either backup, so v2.2
# stays live.
```
