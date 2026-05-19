# x402watch alerts + MCP payment-guidance — deploy

Two independent feature sets ship in this patch:

- **A. Telegram alert hardening** — 6-tier MCP client classifier,
  10-field payment alert, post-settle failure detection, daily KST
  09:00 summary with MCP-tier rollup.
- **B. MCP payment guidance** — 402 response body with x402watch
  differentiators, paid-tool docstring template, free-tool tagline,
  updated `/llms.txt` on the frontend.

These are deliberately separate. Apply A first (so we see the new
alerts arrive), verify, then apply B (which mostly changes user-facing
text). Both leave the PR #36 v2.2 work untouched.

---

## 0. Mandatory pre-flight (do NOT skip)

### 0.1 Confirm PR #36 v2.2 is still live

```bash
curl -s -I https://api.x402.printmoneylab.com/api/v1/health \
  | grep -i x-x402-rewriter
# expect: x-x402-rewriter: v2.2

curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(access-control|x-x402-rewriter):"
# expect: ACAO echo + Expose-Headers + Rewriter v2.2
```

If either check fails, **STOP** and unwind whatever changed since the
PR #36 v2.2 deploy. None of the work in this patch should be applied
on top of a regression.

### 0.2 Confirm the wrapper line is still the last statement in `app/api.py`

```bash
ssh ubuntu@168.138.195.65 \
  "tail -10 /home/ubuntu/x402watch/app/api.py"
# expect: the final non-blank line is `app = X402ResourceRewriter(app)`
```

If that line is anywhere other than at the bottom, fix that first.

### 0.3 Locate the MCP server module

```bash
ssh ubuntu@168.138.195.65 "
  sudo systemctl list-units --type=service | grep x402
  find /home/ubuntu/x402watch -maxdepth 3 -name '*.py' \
    | xargs grep -l 'FastMCP\\|@mcp.tool' 2>/dev/null
"
```

Note the service name (likely `x402watch-mcp.service`) and the file
path (likely `app/mcp_server.py`).

### 0.4 Identify which MCP tools are paid vs free

```bash
ssh ubuntu@168.138.195.65 "
  grep -B1 -A8 '@mcp.tool' /home/ubuntu/x402watch/app/mcp_server.py
"
```

Cross-reference each tool against the paid-endpoint catalogue (the
five paths in §5 of the PR). Anything that internally invokes one of
those five gets the **paid** docstring; everything else stays free.

### 0.5 Telegram bot reuse check

```bash
ssh ubuntu@168.138.195.65 "
  grep -E '^TELEGRAM_BOT_TOKEN=' /home/ubuntu/x402watch/.env
  grep -E '^TELEGRAM_CHAT_ID='   /home/ubuntu/x402watch/.env
  grep -E '^IPINFO_TOKEN='       /home/ubuntu/x402watch/.env || echo 'IPINFO_TOKEN not set (degrades gracefully)'
"
```

---

## 1. Pull the patch onto Oracle

```bash
ssh ubuntu@168.138.195.65
cd /home/ubuntu/x402watch
git fetch origin
git pull --ff-only origin main
ls oracle-patches/x402watch-alerts/
# expect: DEPLOY.md  WIRE_SNIPPETS.py  client_classifier.py
#         daily_summary.py  mcp_payment_hint.py  telegram_notify.py
```

---

## 2. Backups

```bash
cd /home/ubuntu/x402watch/app
for f in main.py api.py mcp_server.py telegram_notify.py disputes_api.py; do
  [ -f "$f" ] && cp "$f" "$f.bak.20260519-alerts"
done
ls -la *.bak.20260519-alerts
```

Note: `app/x402_meta.py` is intentionally NOT backed up here — we are
not touching it.

---

## 3. Install the new modules

```bash
cd /home/ubuntu/x402watch
cp oracle-patches/x402watch-alerts/client_classifier.py   app/client_classifier.py
cp oracle-patches/x402watch-alerts/telegram_notify.py     app/telegram_notify.py
cp oracle-patches/x402watch-alerts/daily_summary.py       app/daily_summary.py
cp oracle-patches/x402watch-alerts/mcp_payment_hint.py    app/mcp_payment_hint.py
```

If `app/telegram_notify.py` already exists (it might — KR Crypto
shares the bot), inspect the existing file before overwriting:

```bash
diff app/telegram_notify.py.bak.20260519-alerts \
     oracle-patches/x402watch-alerts/telegram_notify.py | head -50
```

Decide whether to overwrite or merge based on what's there.

Create the stats helper too (referenced by both api.py and
mcp_server.py snippets):

```bash
cat > app/_stats.py << 'PY'
import json, os
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
PATH = Path(os.environ.get('X402WATCH_STATS_PATH',
                           '/home/ubuntu/x402watch/var/stats.jsonl'))
PATH.parent.mkdir(parents=True, exist_ok=True)

def write(record: dict) -> None:
    record.setdefault('ts', datetime.now(KST).isoformat())
    try:
        with PATH.open('a') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception:
        pass
PY
```

Import sanity:

```bash
cd /home/ubuntu/x402watch
venv/bin/python -c "
from app.client_classifier import classify
from app.telegram_notify import notify_payment, notify_mcp_tool
from app.mcp_payment_hint import payment_required_response, render_paid_docstring
from app.daily_summary import build_daily_text, rollup
from app._stats import write
c = classify('Cursor/0.40.0')
print('classify(Cursor) =>', c)
print('OK')
"
# expect: classify(Cursor) => Classification(tier=2, ...) + OK
```

---

## 4. Wire it up (A — alert hardening)

Open `oracle-patches/x402watch-alerts/WIRE_SNIPPETS.py` and follow
sections **A → E** in order. Each section shows the exact code block
to paste, with comments marking what NOT to touch.

Key rules:
- `app/api.py`: paste payment-success + post-settle-failure hooks in
  the **middle** of the file (next to existing paid handlers). Never
  edit the last 5 lines (`app = X402ResourceRewriter(app)` block).
- `app/mcp_server.py`: paste `_record_mcp_call(...)` near the top and
  call it from every `@mcp.tool` function as the first await.

Restart and watch the logs:

```bash
sudo systemctl restart x402watch-api
sudo systemctl restart x402watch-mcp   # adjust unit name from §0.3
sudo journalctl -u x402watch-api -n 30 --no-pager
sudo journalctl -u x402watch-mcp -n 30 --no-pager
# expect: no ImportError, no telegram errors
```

Smoke from another shell (triggers a known directory bot UA so we can
see the daily-only path taken without spamming the chat):

```bash
curl -s -H "User-Agent: smithery-scanner/1.0" \
  "https://api.x402.printmoneylab.com/api/v1/health"
# Expectation: no immediate Telegram message, but stats.jsonl gets a row.
ssh ubuntu@168.138.195.65 \
  "tail -3 /home/ubuntu/x402watch/var/stats.jsonl"
```

Now trigger an immediate-alert tier by hitting an MCP tool from a
Cursor-style UA (you can simulate by `curl -H "User-Agent: Cursor/0.40"`
the MCP HTTP endpoint, or just open Cursor and call the tool):

```bash
# expect: Telegram message starting with "🔵 MCP call · Tier 2 · Cursor IDE"
```

---

## 5. Wire it up (B — payment guidance)

### 5.1 _call_paid_api 402 response

Apply the snippet from `WIRE_SNIPPETS.py` section **D** to whichever
helper in `app/mcp_server.py` currently wraps the paid HTTP call.
The new `payment_required_response(...)` dict carries the
`value_proposition` + `differentiators` block — that's the
x402watch-specific bit required by the §2 spec.

### 5.2 Paid-tool docstrings (5 tools)

Run §0.4 again to confirm which tools are paid. For EACH paid tool,
replace the docstring with the template in `WIRE_SNIPPETS.py`
section **F**. Update the `$X.XXX` value per the table below.

| Tool wrapping endpoint | Price |
| --- | --- |
| /api/v1/services/{id}/wash-detail | $0.005 |
| /api/v1/services/{id}/transactions | $0.010 |
| /api/v1/categories/{cat}/full-history | $0.020 |
| /api/v1/wash/check | $0.050 |
| /api/v1/buyers/{address}/profile | $0.005 |

### 5.3 Free-tool tagline (everything else)

For each tool that does NOT internally call a paid endpoint, add the
one-line "Free tier" marker from `WIRE_SNIPPETS.py` section **G**.
Do not add the price block or the 🎯 advantage line — that is
intentionally reserved for paid tools so the price signal stays clear.

### 5.4 /llms.txt

The frontend `src/app/llms.txt/route.ts` is already updated in this
commit and will redeploy via Cloudflare Pages on the next git push.
Verify after deploy:

```bash
curl -s https://x402.printmoneylab.com/llms.txt \
  | grep -E "(Paid Endpoints|What makes x402watch different|wash-detail|owner_test)"
# expect: all four matches
```

### 5.5 Restart + smoke

```bash
sudo systemctl restart x402watch-mcp
```

From an MCP client (or a curl-equivalent), call one paid tool without
payment and verify the response now contains:

- `status: "payment_required"`
- `value_proposition`
- `differentiators` (5 entries)
- `merchant_wallets` (Base + Solana addresses)
- `quick_start` (3 steps)
- `compatible_clients`
- `documentation` (3 URLs)

---

## 6. Mandatory post-deploy regression checks

```bash
# 6.1 PR #36 v2.2 rewriter still outermost
curl -s -I https://api.x402.printmoneylab.com/api/v1/health \
  | grep -i x-x402-rewriter
# expect: v2.2

# 6.2 402 CORS triple intact
curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(access-control|x-x402-rewriter|vary):"
# expect: ACAO + Expose-Headers + Vary: Origin + Rewriter v2.2

# 6.3 accepts[].resource still populated
curl -s -i https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail \
  | python3 -c "
import sys, base64, json
for line in sys.stdin:
    if line.lower().startswith('payment-required:'):
        ch = json.loads(base64.b64decode(line.split(':',1)[1].strip()))
        for i,a in enumerate(ch['accepts']):
            print(f'accepts[{i}].resource       :', a.get('resource'))
            print(f'accepts[{i}].extra.resource :', (a.get('extra') or {}).get('resource'))
        break
"
# expect: 4 lines, all = canonical resource URL

# 6.4 Tate's surface check (still 0 findings)
npx --yes x402-surface-check@latest --endpoint --method GET \
  https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail \
  --origin https://x402.printmoneylab.com
```

### 6.5 Real paid-call regression (Moa, manual)

Run one owner-test x402 call on Base and one on Solana against a paid
endpoint. Verify:

- HTTP 200 with the actual paid payload (not a 402).
- A new "💰 유료 결제 성공!" Telegram message arrives with the 10
  fields populated correctly.
- A new row in `var/stats.jsonl` with `kind=payment`.
- The next daily summary (09:00 KST) shows the call under "Payments"
  and the right entry under "top tools".

---

## 7. Rollback (full)

```bash
cd /home/ubuntu/x402watch/app

# Restore patched files
for f in main.py api.py mcp_server.py telegram_notify.py disputes_api.py; do
  [ -f "$f.bak.20260519-alerts" ] && cp "$f.bak.20260519-alerts" "$f"
done

# Remove the new modules
rm -f client_classifier.py daily_summary.py mcp_payment_hint.py _stats.py

# Restart
sudo systemctl restart x402watch-api
sudo systemctl restart x402watch-mcp

# Confirm rewriter is still v2.2 (we never touched it, but verify)
curl -s -I https://api.x402.printmoneylab.com/api/v1/health \
  | grep -i x-x402-rewriter
```

Frontend `llms.txt` rollback is a `git revert` of this commit followed
by a Pages redeploy.

---

## 8. Phase 2 (explicitly out of scope this round)

- Receipt issuance + signed delivery audit (reuse KR Crypto's `merchant_ops.py`).
- OpenAPI `x-payment-info` extensions to eliminate residual AgentCash warnings.
- Catalog metadata (`locale=ko-KR`, etc.).
- Wallet-signed dispute attribution.
- Per-buyer profile page (`/buyers/{address}`).
