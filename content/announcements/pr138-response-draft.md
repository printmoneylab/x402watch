# PR #138 — Tate Lyman audit response draft

**Status:** DRAFT — Moa review before posting to PR #138.
**Target:** solana-foundation/pay-skills (or coinbase/x402 ecosystem listing) PR #138.

---

## Reply draft

Thanks again @TateLyman — all four patch notes addressed. None changed
the paid-route shape; they're the internal/free separation and cache
hygiene you flagged.

**P2 — internal/free routes split from the agent-paid surface.**
The three dispute routes are no longer mixed into the agent-facing
OpenAPI:
- `POST /api/v1/internal/disputes` and `GET /api/v1/internal/disputes/list`
  are bearer-gated internal endpoints — set `include_in_schema=False`,
  so `/openapi.json` no longer advertises them. A defensive prune in
  the OpenAPI builder also drops anything under `/api/v1/internal/`
  in case a future route forgets the flag.
- `GET /api/v1/disputes/buyer/{address}` is a genuine free public API
  (dispute counts, no bodies). It stays in the schema but is now
  unambiguously tagged: `security: []`, `x-x402-free: true`, and a
  `Free — no payment required.` description prefix, so a scanner reads
  it as free rather than as an unlabelled payable surface.

**P3 — `Cache-Control: no-store` on paid 402 + paid 200.**
Every 402 challenge and every paid-endpoint 2xx response now carries
`Cache-Control: no-store`. A 402 is a one-shot challenge; a paid 200
body is data the buyer just paid for — neither should be cached. Free
routes are untouched.

**P3 — `/.well-known/x402` pointer.**
No longer a 404. It returns a tiny machine-readable pointer:
```json
{
  "x402Version": 2,
  "publisher": "PrintMoneyLab",
  "openapi": "https://api.x402.printmoneylab.com/openapi.json",
  "mcp": "https://api.x402.printmoneylab.com/mcp",
  "documentation": "https://x402.printmoneylab.com/docs/methodology"
}
```
Cached `public, max-age=3600` since it rarely changes. Crawlers that
start discovery at `/.well-known/` now get a direct hop to the OpenAPI
doc and the MCP endpoint.

**P3 — MCP handshake documented.**
`GET /mcp` returns 406 by design — the streamable-HTTP transport
requires the SSE-style `Accept` header. The ecosystem listing entry
now documents the handshake explicitly (see the PR description update
below) so a scanner doesn't read the 406 as a false negative.

Net: internal/free API surface is now separated from the agent-paid
surface, and paid responses declare their cache policy. Appreciate the
thorough pass.

---

## PR #138 description — add this block

> **MCP endpoint usage.** `https://api.x402.printmoneylab.com/mcp` is a
> Model Context Protocol server over streamable HTTP. It requires the
> handshake header:
>
> ```
> Accept: application/json, text/event-stream
> ```
>
> A plain `GET /mcp` without that `Accept` returns `406 Not Acceptable`
> — this is expected transport behaviour, not an outage. Initialise
> with a standard MCP `initialize` request. Five read-only tools:
> `x402_get_categories`, `x402_get_service`, `x402_check_wash`,
> `x402_search_services`, `x402_get_trends` (all free).

---

## Verification commands (post-deploy — paste results into the PR if asked)

```bash
# P2 — internal routes gone from the public OpenAPI
curl -s https://api.x402.printmoneylab.com/openapi.json \
  | python3 -c "import json,sys; p=json.load(sys.stdin)['paths']; \
print('internal paths still present:', [k for k in p if '/internal/' in k] or 'none'); \
print('buyer route present:', '/api/v1/disputes/buyer/{address}' in p)"
# expect: internal paths → none ; buyer route → True

# P3 — 402 carries Cache-Control: no-store
curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(cache-control|x-x402-rewriter|access-control-allow-origin):"
# expect: cache-control: no-store ; x-x402-rewriter: v2.4 ; ACAO echoed

# P3 — /.well-known/x402 no longer 404
curl -s -o /dev/null -w "%{http_code}\n" \
  https://api.x402.printmoneylab.com/.well-known/x402
# expect: 200
curl -s https://api.x402.printmoneylab.com/.well-known/x402 | python3 -m json.tool

# P3 — MCP handshake (406 without Accept is expected)
curl -s -o /dev/null -w "no Accept: %{http_code}\n" \
  https://api.x402.printmoneylab.com/mcp
# expect: 406

# Regression — Tate's earlier suite still clean
npx --yes x402-surface-check@latest --endpoint --method GET \
  https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail \
  --origin https://x402.printmoneylab.com
```

---

## Deploy (Moa, on Oracle)

```bash
cd /home/ubuntu/x402watch
git fetch origin && git pull --ff-only origin main

# back up + install the two changed modules
cp app/x402_meta.py    app/x402_meta.py.bak.20260520-pr138
cp app/disputes_api.py app/disputes_api.py.bak.20260520-pr138
cp oracle-patches/pr36-openapi/x402_meta.py     app/x402_meta.py
cp oracle-patches/step6-disputes/disputes_api.py app/disputes_api.py

# import sanity
venv/bin/python -c "from app.x402_meta import setup_x402_meta, is_paid_path, REWRITER_VERSION; print(REWRITER_VERSION, is_paid_path('/api/v1/wash/check'))"
# expect: v2.4 True

sudo systemctl restart x402watch-api
sudo journalctl -u x402watch-api -n 20 --no-pager | grep -E "x402_meta|well-known|ERROR"
# expect: "x402_meta installed: 5 paid endpoints, … /.well-known/x402 pointer"
```

Then run the verification block above.

## Regression invariants (must stay green)

- `x-x402-rewriter` header bumps `v2.3 → v2.4` — that IS the deploy
  confirmation.
- 402 still carries the CORS triple (ACAO echo + Expose-Headers +
  Vary: Origin) from PR #36 v2.2/v2.3 — `_inject_cors` is unchanged
  in behaviour; `no-store` is added by the separate `_with_no_store`.
- `accepts[].resource` injection (PR #36) unchanged.
- Attribute proxy `__getattr__` (v2.3) unchanged — `app.state.redis`
  still resolves.
- Step 6 dispute system: routes still work, just hidden from schema.

## Rollback

```bash
cp app/x402_meta.py.bak.20260520-pr138    app/x402_meta.py
cp app/disputes_api.py.bak.20260520-pr138 app/disputes_api.py
sudo systemctl restart x402watch-api
```
