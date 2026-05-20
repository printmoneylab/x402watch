# PR #138 audit fixes — deploy

Tate Lyman's second audit (2026-05-20) on the coinbase/x402 ecosystem
listing. Four items, none merge-blocking. Fixes for P2 + the three P3s.

| Item | Fix | File |
|---|---|---|
| P2 — internal/free routes mixed into the paid OpenAPI surface | hide the two `internal/` dispute routes (`include_in_schema=False`), tag the public buyer-counts route `free` + `security: []` | `app/disputes_api.py` |
| P3.1 — no cache policy on paid 402 / paid 200 | rewriter stamps `Cache-Control: no-store` on every 402 and on 2xx for paid paths | `app/x402_meta.py` (rewriter → v2.4) |
| P3.2 — `/.well-known/x402` 404 | tiny JSON pointer route (openapi / mcp / docs) | `app/x402_meta.py` (`setup_x402_meta`) |
| P3.3 — `GET /mcp` 406 looks like a failure to crawlers | document the streamable-HTTP handshake in the PR description — no code change | PR #138 text |

PR #36 v2.3 stays intact — same `X402ResourceRewriter`, now v2.4
(ACAO + expose-headers + Vary unchanged, `no-store` added).

---

## 0. Pre-flight

```bash
curl -s -I https://api.x402.printmoneylab.com/api/v1/health | grep -i x-x402-rewriter
# expect: v2.3  (becomes v2.4 after this deploy)
```

## 1. Pull

```bash
cd /home/ubuntu/x402watch
git fetch origin && git pull --ff-only origin main
```

## 2. P3.1 + P3.2 — x402_meta.py

```bash
cp app/x402_meta.py app/x402_meta.py.bak.20260520-pr138
cp oracle-patches/pr36-openapi/x402_meta.py app/x402_meta.py
venv/bin/python -c "
from app.x402_meta import REWRITER_VERSION, is_paid_path, WELL_KNOWN_X402
print('REWRITER_VERSION:', REWRITER_VERSION)          # expect v2.4
print('is_paid_path wash-detail:', is_paid_path('/api/v1/services/1/wash-detail'))  # True
print('well-known keys:', sorted(WELL_KNOWN_X402))
"
```

No api.py change needed — `setup_x402_meta(app)` is already called
there (PR #36) and now also mounts `/.well-known/x402`. The
`app = X402ResourceRewriter(app)` wrapper line is unchanged.

## 3. P2 — disputes_api.py

```bash
cp app/disputes_api.py app/disputes_api.py.bak.20260520-pr138
cp oracle-patches/step6-disputes/disputes_api.py app/disputes_api.py
venv/bin/python -c "from app.disputes_api import router; print('disputes router OK, routes:', len(router.routes))"
```

## 4. Restart

```bash
sudo systemctl restart x402watch-api
sudo journalctl -u x402watch-api -n 20 --no-pager | grep -E "x402_meta|ERROR|startup"
# expect: "x402_meta installed: 5 paid endpoints, 2 accepts entries,
#          /.well-known/x402 pointer ..."
```

## 5. Verification — each item

```bash
# P3.1 — paid 402 carries no-store
curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(cache-control|x-x402-rewriter|access-control|payment-required):"
# expect: cache-control: no-store
#         x-x402-rewriter: v2.4
#         access-control-allow-origin / -expose-headers still present

# P3.1 — paid 200 also carries no-store (run a real owner-test payment,
# or just confirm the header machinery on the 402 above; the 200 path
# uses the same is_paid_path gate)

# P3.2 — /.well-known/x402 returns the pointer, not 404
curl -s -w "\nhttp=%{http_code}\n" https://api.x402.printmoneylab.com/.well-known/x402
# expect: http=200, JSON with openapi / mcp / documentation

# P2 — internal routes gone from /openapi.json, free route tagged
curl -s https://api.x402.printmoneylab.com/openapi.json | python3 -c "
import json,sys
d=json.load(sys.stdin); paths=d.get('paths',{})
print('internal/disputes present:', '/api/v1/internal/disputes' in paths, '(expect False)')
print('internal/disputes/list present:', '/api/v1/internal/disputes/list' in paths, '(expect False)')
bp=paths.get('/api/v1/disputes/buyer/{address}',{}).get('get',{})
print('buyer-counts tags:', bp.get('tags'), '(expect [free])')
print('buyer-counts security:', bp.get('security'), '(expect [])')
"
```

## 6. Regression — PR #36 v2.x must stay green

```bash
# Tate's surface check — still 0 P2/P3 findings on the paid routes
npx --yes x402-surface-check@latest --endpoint --method GET \
  https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail \
  --origin https://x402.printmoneylab.com

# accepts[].resource still populated
curl -s -i https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail \
  | grep -i "^payment-required:" | cut -d' ' -f2 \
  | python3 -c "import base64,json,sys; ch=json.loads(base64.b64decode(sys.stdin.read().strip())); print('accepts[0].resource:', ch['accepts'][0].get('resource'))"

# dispute system still works (the routes are hidden from OpenAPI but
# still served)
curl -s "https://x402.printmoneylab.com/api/disputes/buyer/0x15c3cdaeb8a0f00bb3a05f2bbbd86f0eebcd49c0"
# expect: 200 JSON
```

## 7. Rollback

```bash
cp app/x402_meta.py.bak.20260520-pr138    app/x402_meta.py
cp app/disputes_api.py.bak.20260520-pr138 app/disputes_api.py
sudo systemctl restart x402watch-api
```

Reverts to v2.3 (no `no-store`, no `/.well-known/x402`, internal
routes back in OpenAPI). PR #36 behaviour otherwise unchanged.
