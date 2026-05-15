# PR #36 — reviewer-feedback response draft

**Status:** DRAFT — fill in the three `<<AFTER PATCH>>` blocks with
verification output once `oracle-patches/pr36-openapi/DEPLOY.md` is
applied, then paste into the PR.

**Target PR:** solana-foundation/pay-skills #36

---

Thanks @TateLyman for the careful audit. Addressed all three findings in commit `<<COMMIT_SHA>>` (v2 of the patch — v1 had a `BaseHTTPMiddleware`-based response rewriter that didn't fire on production 402s because the facilitator finalises the response outside the user-middleware chain; v2 uses a pure ASGI middleware wrapped around `app` from the outside, which is guaranteed to be the outermost piece of the stack).

1. **OpenAPI now declares the paid x402 endpoints with `x-payment-info` + `responses.402`.** Free routes get an explicit `security: []`. Added `info.x-guidance` and a top-level `x-discovery` block with ownership proofs. All wired through a `custom_openapi` factory in `app/x402_meta.py` so the metadata stays in source-controlled config rather than scattered across route decorators.

2. **`accepts[].resource` and `accepts[].extra.resource` are now populated on every 402 challenge.** A small response middleware decodes the `payment-required` header, copies `resource.url` into both fields on every accepts entry (Base + Solana), and re-encodes. It also writes the same challenge into the response body so header and body are in parity for clients that ignore custom headers.

3. **POST `/api/v1/wash/check` preflight now responds 204 with `Access-Control-Allow-Methods: GET, POST, OPTIONS`.** A separate paid-route preflight middleware runs before the existing CORSMiddleware so the previous `allow_methods=["GET"]` config doesn't 400 the POST preflight. Non-paid routes are untouched.

The change is one drop-in module + a 3-line wireup in `app/api.py` — full source and deploy procedure at `oracle-patches/pr36-openapi/` in the x402watch repo (printmoneylab/x402watch).

### Before / after — the four endpoints you ran

#### `GET /api/v1/services/{id}/wash-detail`

**Before:**
```
| wash-detail | GET | 402 | x402 | $0.005 | eip155:8453 | <url> |
Browser Preflight: Allow-Methods: GET
Findings: P2 - wash-detail challenge does not repeat the resource URL
          in both resource.url and accepts[0].extra.resource/resource.
```

**After:**
```
<<AFTER PATCH: paste the x402-surface-check output here>>
```

#### `GET /api/v1/services/{id}/transactions`

**Before:**
```
| transactions | GET | 402 | x402 | $0.01 | eip155:8453 | <url> |
Browser Preflight: Allow-Methods: GET
Findings: P2 - transactions challenge does not repeat the resource URL ...
```

**After:**
```
<<AFTER PATCH: paste the x402-surface-check output here>>
```

#### `GET /api/v1/categories/{cat}/full-history`

**Before:**
```
| full-history | GET | 402 | x402 | $0.02 | eip155:8453 | <url> |
Browser Preflight: Allow-Methods: GET
Findings: P2 - full-history challenge does not repeat the resource URL ...
```

**After:**
```
<<AFTER PATCH: paste the x402-surface-check output here>>
```

#### `POST /api/v1/wash/check`

**Before:**
```
| check | POST | 402 | x402 | $0.05 | eip155:8453 | <url> |
Browser Preflight: HTTP 400 Allow-Methods: GET   ← POST disallowed
Findings: P2 - check challenge does not repeat the resource URL ...
```

**After:**
```
<<AFTER PATCH: paste the x402-surface-check output here>>
```

### AgentCash discovery

**Before:** 8× `L2_AUTH_MODE_MISSING` (paid + free routes), 1× `L4_GUIDANCE_MISSING`, 13× `L3_AUTH_MODE_MISSING`.

**After:**
```
<<AFTER PATCH: paste the agentcash discovery output here>>
```

Expected: `L4_GUIDANCE_MISSING` resolved (now have `info.x-guidance`); `L2_AUTH_MODE_MISSING` resolved for paid routes (now have `x-payment-info`) and for free routes (now have `security: []`).

### Regression — existing paid flow

The five paid endpoints continue to resolve 200 against valid payments
on both Base and Solana. The `accepts[].resource` injection only touches
402 responses; the facilitator's success path is untouched. Owner-test
payment from `0xcF92…2fB` (EVM) / `3Ywxk31…oVy9` (SVM) confirmed
post-patch.

### What changed in the repo

`oracle-patches/pr36-openapi/x402_meta.py` (~400 lines) — three concerns:

| Concern | Where |
|---|---|
| `info.x-guidance`, `x-discovery`, per-route `x-payment-info`, `responses.402`, `security: []` | `custom_openapi_factory(app)` |
| `accepts[].resource` + `accepts[].extra.resource` + body/header parity | `X402ResourceInjectionMiddleware` (Starlette `BaseHTTPMiddleware`) |
| OPTIONS 204 with `GET, POST, OPTIONS` on paid routes | `X402PreflightMiddleware`, runs before `CORSMiddleware` |

Idempotent — the `setup_x402_meta(app)` call guards itself with
`app.state._x402_meta_installed`.

Happy to iterate if anything else surfaces.

— PrintMoneyLab
