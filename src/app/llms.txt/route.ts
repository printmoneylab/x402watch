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

## Classification Labels

Each x402 buyer is classified into one of 8 mutually-exclusive labels:

- exchange_user: Funded from CEX hot wallet
- self_test: Operator test traffic
- verifier: Catalog crawler bot
- analytics_bot: Established research bot
- ai_agent: Multi-purpose AI agent (organic)
- developer: Single-service heavy bot
- organic_user: Uncategorized organic
- suspected_wash: Pattern-matched wash trading

## Wash Detection Methodology

Cohort signals + vanity clustering + concentration analysis.
Full methodology: https://github.com/printmoneylab/x402watch/blob/main/docs/wash-filter-methodology.md

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
