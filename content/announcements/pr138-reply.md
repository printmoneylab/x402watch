# PR #138 — Tate Lyman audit reply draft

**Status:** DRAFT — Moa posts after the Oracle deploy + verification.
**Target:** coinbase/x402 ecosystem listing PR #138.

---

## Reply to Tate

Thanks for the second pass @TateLyman — all four addressed in commit `<<COMMIT_SHA>>`.

**P2 — internal/free routes mixed into the paid OpenAPI surface.**
You're right that the dispute routes were noise for a payment-first
scanner. Split done:
- `/api/v1/internal/disputes` and `/api/v1/internal/disputes/list` are
  internal (bearer-gated, called only by our own Edge proxy) — removed
  from `/openapi.json` entirely (`include_in_schema=False`).
- `/api/v1/disputes/buyer/{address}` is a genuine free public route, so
  it stays in the schema but is now tagged `free` with `security: []`,
  so a scanner reads it as "free, no payment" rather than a paid route
  that failed validation.
The paid surface in `/openapi.json` is now exactly the five x402
endpoints, each with `x-payment-info` + a `402` response.

**P3 — Cache-Control on paid surfaces.** The ASGI rewriter (the same
one that fixes `accepts[].resource` from your first audit) now stamps
`Cache-Control: no-store` on every 402 challenge and on `2xx`
responses for paid endpoint paths. A challenge is one-shot and a paid
`200` is data the buyer just paid for — neither should sit in a shared
cache. Free routes are untouched. Verifiable: `curl -I` a paid 402 now
shows `cache-control: no-store` alongside `x-x402-rewriter: v2.4`.

**P3 — `/.well-known/x402`.** Added a tiny JSON pointer there:

```json
{
  "x402Version": 2,
  "publisher": "PrintMoneyLab",
  "openapi": "https://api.x402.printmoneylab.com/openapi.json",
  "mcp": "https://api.x402.printmoneylab.com/mcp",
  "documentation": "https://x402.printmoneylab.com/docs/methodology"
}
```

No longer a 404; well-known-first crawlers get a one-hop pointer to the
OpenAPI doc and the MCP endpoint.

**P3 — `GET /mcp` 406.** That 406 is correct streamable-HTTP behaviour
(the transport requires the SSE-style `Accept`), but you're right that
a crawler with no MCP context reads it as a failure. Rather than weaken
the transport we've documented the handshake in this PR's description
(below) so the listing carries the context. Happy to add a short
human-readable hint body to the 406 if you think that's worth it.

Net: the paid OpenAPI surface is now just the five x402 endpoints;
internal/free routes are clearly separated; paid responses declare
`no-store`; `/.well-known/x402` resolves. Appreciate the thorough
pass — these were all real polish gaps.

— PrintMoneyLab

---

## PR #138 description — add this "MCP endpoint" subsection

> ### MCP server
>
> x402watch also exposes a Model Context Protocol server over
> **streamable HTTP**:
>
> - **Endpoint:** `https://api.x402.printmoneylab.com/mcp`
> - **Transport:** streamable-http (not SSE, not stdio)
> - **Handshake:** the endpoint requires
>   `Accept: application/json, text/event-stream`. A plain
>   `GET /mcp` without that `Accept` returns `406 Not Acceptable` —
>   this is expected; it is not an outage. Initialise with a standard
>   MCP `initialize` request over a POST carrying both Accept types.
> - **Tools:** 5 read-only wrappers over the public API
>   (`x402_get_categories`, `x402_get_service`, `x402_check_wash`,
>   `x402_search_services`, `x402_get_trends`) — all free.
>
> Example probe that a listing crawler can use without a false negative:
>
> ```bash
> curl -sS https://api.x402.printmoneylab.com/mcp \
>   -H "Accept: application/json, text/event-stream" \
>   -H "Content-Type: application/json" \
>   -d '{"jsonrpc":"2.0","id":1,"method":"initialize",
>        "params":{"protocolVersion":"2025-06-18",
>                  "capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
> ```

---

## Verification commands (Moa runs post-deploy, paste results into the reply)

```bash
# P3.1
curl -s -D - -o /dev/null \
  "https://api.x402.printmoneylab.com/api/v1/services/833049/wash-detail" \
  -H "Origin: https://x402.printmoneylab.com" \
  | grep -iE "^(cache-control|x-x402-rewriter):"
# → cache-control: no-store / x-x402-rewriter: v2.4

# P3.2
curl -s -w "  [http %{http_code}]\n" https://api.x402.printmoneylab.com/.well-known/x402

# P2
curl -s https://api.x402.printmoneylab.com/openapi.json \
  | python3 -c "import json,sys; p=json.load(sys.stdin)['paths']; print('internal routes in schema:', [k for k in p if 'internal' in k])"
# → internal routes in schema: []
```
