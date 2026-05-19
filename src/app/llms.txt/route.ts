/**
 * llms.txt — discovery hint for LLM crawlers, served at /llms.txt.
 *
 * Lives as a route handler (rather than public/llms.txt) so the endpoint
 * list and timestamps can drift with the codebase without anyone needing
 * to remember to keep a static file in sync.
 */

const SITE_URL = "https://x402.printmoneylab.com";
const API_BASE = "https://api.x402.printmoneylab.com/api/v1";

const BODY = `# x402watch

> Wash-filtered intelligence layer for the x402 ecosystem.
> Free public data, open methodology, AI-native API.

## About

x402watch indexes 36,000+ x402 services across 4 chains (Base, Solana, Polygon, Arbitrum), classifies them with AI, and detects wash trading patterns using cohort signal analysis. All data is published daily under CC0 license.

## Key Resources

- Live dashboard: ${SITE_URL}
- Public API: ${API_BASE}
- Open dataset: https://github.com/printmoneylab/x402watch-data
- Source code: https://github.com/printmoneylab/x402watch
- Methodology: ${SITE_URL}/wash-report

## What makes x402watch different

x402watch is not a generic indexer. It's a wash-filtered intelligence
layer for the x402 ecosystem.

Key differentiators:

- 4-layer wash detection algorithm (v2.0, 2026-04-30): per-seller flags
  → per-(buyer, seller) labels → global guards → tx-weighted majority
  for the global buyer label.
- 9-label buyer taxonomy (organic_user, ai_agent, self_test,
  suspected_wash, owner_test, exchange_user, verifier, analytics_bot,
  developer).
- Per-(buyer, seller) labels — the same buyer can be labelled
  differently on different services.
- Open methodology — every threshold and rule public at
  ${SITE_URL}/docs/methodology.
- Dispute system — false positives can be reported via POST /api/disputes;
  ≥ 5 independent reports auto-trigger a recompute on the next daily run.

Verified false-positive resolution: KR Crypto kr-prices went from 96.4%
suspected_wash → 0%. Verified true-positive retention: Aubrai 99.98% wash.

For merchants: audit your own buyer traffic with the same intelligence
layer used across the entire x402 ecosystem.

For AI agents: verify endpoint quality before auto-spending — wash-
filtered data prevents budget loss on fake-traffic endpoints.

## API Endpoints (Free)

### GET /api/v1/landing-stats
Real-time market overview: indexed services, transactions, active buyers, real volume %.

### GET /api/v1/categories
List of 33 x402 service categories with stats (volume, transactions, label distribution).

### GET /api/v1/categories/{slug}
Detail for single category: time-series, top services, label breakdown.

### GET /api/v1/services
Paginated list of all indexed x402 services with filtering (category, chain, price, real %).

### GET /api/v1/services/{id}
Detail for single service: stats, time-series, buyer labels, top buyers.

### GET /api/v1/trends
Daily trends: new services, volume movers, hot services.

### GET /api/v1/wash-report
Aggregate wash detection: label distribution, anonymized case studies.

### GET /api/v1/disputes/buyer/{address}
Public dispute counts (total, pending, reviewed, resolved) for a buyer wallet.

## Paid Endpoints (x402 micropayments)

All paid endpoints accept USDC on Base or Solana mainnet. Replay with
the \`X-Payment: <signed-payload>\` header after the 402 challenge.

| Endpoint | Method | Price | Returns |
| --- | --- | --- | --- |
| /api/v1/services/{id}/wash-detail | GET | $0.005 | Top 50 buyers with full label classification, confidence scores, signal-by-signal breakdown. |
| /api/v1/services/{id}/transactions | GET | $0.010 | Full transaction history for a service (paginated). |
| /api/v1/categories/{cat}/full-history | GET | $0.020 | Full daily time-series and label distribution for a category. |
| /api/v1/wash/check | POST | $0.050 | On-demand wash-filter evaluation of an arbitrary (buyer, seller) pair. |
| /api/v1/buyers/{address}/profile | GET | $0.005 | Global label + per-pair breakdown + dispute count for a buyer wallet. |

## How AI agents pay

1. Install an x402 client: AgentCash, Pay.sh, or the official x402 SDK.
2. Fund a wallet with USDC on Base or Solana mainnet (≥ price for the call).
3. GET / POST the endpoint to receive a 402 with a \`payment-required\` header
   (base64-encoded JSON challenge) plus an identical challenge in the body.
4. Sign the payment via the facilitator and replay with the \`X-Payment\`
   header. Successful responses return the actual paid payload.

## Merchant Wallets

- Base:   0xcF9223eCe895258dEa8D288AEBcf846Ab8E342fB
- Solana: 3Ywxk31SvWKwZBdY6bLvjmn5h4mzWcT3HJ5UZbYXoVy9

## Browser CORS support

402 responses carry \`Access-Control-Allow-Origin\` (echoes the request Origin),
\`Access-Control-Expose-Headers: payment-required, x-x402-rewriter\`, and
\`Vary: Origin\`, so browser \`fetch()\` clients can read both the body and the
challenge header. POST endpoints (e.g. /api/v1/wash/check) support OPTIONS
preflight with \`Access-Control-Allow-Methods: GET, POST, OPTIONS\`.

## Classification Labels

Each (buyer, seller) pair is classified into one of 9 mutually-exclusive labels:

- exchange_user: Buyer wallet IS a labelled CEX hot wallet (whitelist match).
- self_test: Operator validating their own endpoint.
- verifier: Directory / discovery crawler bot.
- analytics_bot: Established periodic data-scraping bot.
- ai_agent: LLM-driven multi-service consumer.
- developer: Single-service heavy bot / backtest burst.
- organic_user: Default — none of the above signals fired strongly.
- suspected_wash: Structural signals consistent with manufactured volume.
- owner_test: Operator's whitelisted self-test wallets (excluded from rollup denominator).

A buyer's global label is the tx-weighted majority across their pair labels.

## Wash Detection Methodology

v2.0 four-layer pipeline: per-seller flags → per-(buyer, seller) pair labels
→ global-context guards → tx-weighted derivation of the global buyer label.
Full methodology: ${SITE_URL}/docs/methodology

## MCP Server

- Endpoint: ${API_BASE.replace("/api/v1", "")}/mcp (transport: streamable-http)
- Registry: https://registry.modelcontextprotocol.io
- Server name: io.github.printmoneylab/x402watch
- Smithery: https://smithery.ai/servers/bakyang2/x402watch

## Data Updates

- Service indexing: hourly
- Transaction indexing: hourly
- Label recalculation: daily (KST 09:30)
- Public dataset commits: daily (UTC 04:00)

## License

- Code: Apache 2.0
- Data: CC0 (public domain)

## Contact

- GitHub Issues: https://github.com/printmoneylab/x402watch/issues
- Twitter: @printmoneylab
`;

export const dynamic = "force-static";

export function GET(): Response {
  return new Response(BODY, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      // Mid-length cache; the file is small and rarely changes.
      "Cache-Control": "public, max-age=300, s-maxage=3600",
    },
  });
}
