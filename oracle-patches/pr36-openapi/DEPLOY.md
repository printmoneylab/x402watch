# PR #36 reviewer-feedback patch — deploy

Three fixes for Tate Lyman's PR #36 audit on x402watch:

1. OpenAPI declares paid endpoints with `x-payment-info` + 402 responses + free routes get `security: []`.
2. 402 challenges repeat `resource` in `accepts[i].resource` and `accepts[i].extra.resource`; body matches header.
3. OPTIONS preflight on paid endpoints returns 204 with `Access-Control-Allow-Methods: GET, POST, OPTIONS`.

Everything is a single drop-in module + a 3-line wireup in `app/api.py`. No DB changes. ~5 min apply, <2 min rollback.

---

## 0. Inputs

| Item | Value |
|---|---|
| Server | `ubuntu@168.138.195.65` |
| Repo | `/home/ubuntu/x402watch/` |
| FastAPI entrypoint | `/home/ubuntu/x402watch/app/api.py` |
| Service | `x402watch-api.service` (port 8090) |
| Domain | `https://api.x402.printmoneylab.com` |

---

## 1. Pull the patch onto Oracle

```bash
cd /home/ubuntu/x402watch
git fetch origin
git pull --ff-only origin main
ls oracle-patches/pr36-openapi/
# expect: DEPLOY.md  x402_meta.py
```

---

## 2. Backup + install module

```bash
cp /home/ubuntu/x402watch/app/api.py \
   /home/ubuntu/x402watch/app/api.py.bak.20260515-pr36

cp /home/ubuntu/x402watch/oracle-patches/pr36-openapi/x402_meta.py \
   /home/ubuntu/x402watch/app/x402_meta.py
```

Verify the module imports cleanly without touching the live server:
```bash
cd /home/ubuntu/x402watch
venv/bin/python -c "from app.x402_meta import setup_x402_meta, PAID_ENDPOINTS; print('OK', len(PAID_ENDPOINTS), 'paid endpoints')"
# expect: OK 5 paid endpoints
```

---

## 3. Wire it up in `app/api.py`

Open `/home/ubuntu/x402watch/app/api.py` and add this **at the very
bottom of the file**, after every `app.add_middleware(...)`, every
`@app.get / @app.post`, every `app.include_router(...)`, and every
other module-level assignment of `app`:

```python
# PR #36 reviewer feedback — paid-endpoint OpenAPI + accepts.resource
# parity + POST preflight. See oracle-patches/pr36-openapi/.
from app.x402_meta import setup_x402_meta, X402ResourceRewriter
setup_x402_meta(app)             # OpenAPI x-payment-info + OPTIONS preflight
app = X402ResourceRewriter(app)  # ASGI wrapper — outermost, guarantees 402 rewrite
```

The order matters and the **final line must reassign `app`**. uvicorn
loads `app.api:app` at import time, so whatever `app` points to at the
end of the module is what handles requests. Wrapping it in
`X402ResourceRewriter` outside the FastAPI stack guarantees the
middleware sits outside the facilitator middleware, CORS middleware,
and exception handlers — the previous v1 wireup used a
`BaseHTTPMiddleware` for this and it did not fire on the live 402
because the facilitator finalised the response before the dispatcher
saw it. v2 fixes that with pure ASGI buffering.

`setup_x402_meta` is idempotent. Calling `X402ResourceRewriter(app)`
more than once would double-wrap — only do it once at the end of the
module.

If `app/api.py` and `app/main.py` both exist and the FastAPI app is
constructed in `main.py`, add the same three lines to `main.py`
instead — but only in the file that exports `app`.

---

## 4. Restart + smoke

```bash
sudo systemctl restart x402watch-api
sudo systemctl status x402watch-api --no-pager | head -20
sudo journalctl -u x402watch-api -n 30 --no-pager | grep -E "x402_meta|ERROR|startup"
# expect: "x402_meta installed: 5 paid endpoints, 2 accepts entries (rewriter mounted separately)"

# Two-second check that the ASGI rewriter is in the chain — every
# response gets `X-X402-Rewriter: v2.2` (`v2.2-noop` for 402s with no
# decodable challenge). If the tracer header is missing,
# X402ResourceRewriter is not the outermost — re-read step 3.
curl -s -I "https://api.x402.printmoneylab.com/api/v1/health" | grep -i x-x402-rewriter
# expect: x-x402-rewriter: v2.2

# CORS-on-402 check: 402 responses must carry Access-Control-Allow-Origin
# (echoing the request Origin) + Access-Control-Expose-Headers covering
# payment-required, so browser fetch() can read both the body and the
# challenge header. The facilitator emits 402s outside the user-middleware
# chain so the existing CORSMiddleware never injects these — v2.2 of the
# rewriter does.
curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(access-control|x-x402-rewriter):"
# expect:
#   access-control-allow-origin: https://x402.printmoneylab.com
#   access-control-expose-headers: payment-required, x-x402-rewriter
#   x-x402-rewriter: v2.2
# plus a `Vary:` header that includes Origin.
```

Quick local smoke (no internet round-trip):
```bash
curl -s http://127.0.0.1:8090/openapi.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('has info.x-guidance:', 'x-guidance' in d.get('info', {}))
print('has x-discovery   :', 'x-discovery' in d)
for p in ['/api/v1/services/{id}/wash-detail',
          '/api/v1/services/{id}/transactions',
          '/api/v1/categories/{cat}/full-history',
          '/api/v1/wash/check',
          '/api/v1/buyers/{address}/profile']:
    op = (d.get('paths', {}).get(p) or {})
    for m, o in op.items():
        print(f'  {m.upper():<4} {p}: x-payment-info={\"x-payment-info\" in o}, 402={\"402\" in (o.get(\"responses\") or {})}')
"
# expect: True / True / all 5 endpoints showing x-payment-info=True, 402=True
```

---

## 5. Tate's verification suite — re-run

These are the exact commands Tate ran in the audit. Paste the output
into the PR #36 response.

```bash
npx --yes x402-surface-check@0.2.13 --endpoint --method GET \
  https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail \
  --origin https://x402.printmoneylab.com

npx --yes x402-surface-check@0.2.13 --endpoint --method GET \
  https://api.x402.printmoneylab.com/api/v1/services/833049/transactions \
  --origin https://x402.printmoneylab.com

npx --yes x402-surface-check@0.2.13 --endpoint --method GET \
  https://api.x402.printmoneylab.com/api/v1/categories/maps_location/full-history \
  --origin https://x402.printmoneylab.com

npx --yes x402-surface-check@0.2.13 --endpoint --method POST \
  https://api.x402.printmoneylab.com/api/v1/wash/check \
  --origin https://x402.printmoneylab.com

npx -y @agentcash/discovery@latest discover "https://api.x402.printmoneylab.com"
```

Expected after-state:
- All four `x402-surface-check` runs report **no `P2 - … challenge does not repeat the resource URL …`** finding.
- POST `/wash/check` preflight row shows `Allow-Methods: GET, POST, OPTIONS` and `HTTP: 204`.
- AgentCash discovery: `L4_GUIDANCE_MISSING` gone; `L2_AUTH_MODE_MISSING` gone for paid routes (they now declare x-payment-info) and gone for free routes (they now declare `security: []`).

---

## 6. Regression smoke — existing paid flow

Confirm the existing facilitator-driven paid path still works end-to-end
by checking the 402 challenge shape:

```bash
curl -s -i "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  | grep -i "^payment-required:" \
  | cut -d' ' -f2 \
  | python3 -c "
import base64, json, sys
ch = json.loads(base64.b64decode(sys.stdin.read().strip()))
print('top resource:', ch['resource']['url'])
for i, a in enumerate(ch['accepts']):
    print(f'accepts[{i}] resource:        {a.get(\"resource\")}')
    print(f'accepts[{i}] extra.resource:  {(a.get(\"extra\") or {}).get(\"resource\")}')
"
# expect: top resource and BOTH accepts[i].resource and accepts[i].extra.resource
# pointing at the same URL for both Base (i=0) and Solana (i=1).
```

Body parity:
```bash
curl -s "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('body has accepts?', 'accepts' in d, '  count=', len(d.get('accepts', [])))
"
# expect: body has accepts? True   count= 2
```

POST preflight:
```bash
curl -s -i -X OPTIONS "https://api.x402.printmoneylab.com/api/v1/wash/check" \
  -H "Origin: https://x402.printmoneylab.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-payment" \
  | head -10
# expect: HTTP/1.1 204, Access-Control-Allow-Methods: GET, POST, OPTIONS
```

Owner-test payment (Moa's wallet) — confirm a real 200 still resolves:
```bash
# Moa runs from local x402 client — left as a manual check.
```

---

## 7. Rollback (full, < 2 min)

```bash
cp /home/ubuntu/x402watch/app/api.py.bak.20260515-pr36 \
   /home/ubuntu/x402watch/app/api.py
rm /home/ubuntu/x402watch/app/x402_meta.py
sudo systemctl restart x402watch-api
```

The two added lines in `app/api.py` are the only edit. Restoring the
backup is the rollback. No DB state to undo.
