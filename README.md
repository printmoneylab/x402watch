# x402watch

> Wash-filtered intelligence layer for the x402 ecosystem — free public dashboard, daily CC0 datasets, x402-native paid API, and a remote MCP server.

[![Live](https://img.shields.io/badge/live-x402.printmoneylab.com-3ee0a3)](https://x402.printmoneylab.com)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Data: CC0](https://img.shields.io/badge/data-CC0-lightgrey)](https://github.com/printmoneylab/x402watch-data)
[![MCP Registry](https://img.shields.io/badge/MCP%20Registry-io.github.printmoneylab%2Fx402watch-7c3aed)](https://registry.modelcontextprotocol.io/v0/servers?search=printmoneylab)
[![Smithery](https://img.shields.io/badge/Smithery-bakyang2%2Fx402watch-1f6feb)](https://smithery.ai/servers/bakyang2/x402watch)
[![Glama](https://glama.ai/mcp/servers/printmoneylab/x402watch/badge)](https://glama.ai/mcp/servers/printmoneylab/x402watch)

## What is x402watch

Public x402 dashboards count transactions. **x402watch classifies them.**

Every active buyer wallet is tagged with one of eight labels — `organic_user`, `self_test`, `developer`, `suspected_wash`, `ai_agent`, `analytics_bot`, `exchange_user`, or `verifier` — using cohort signals + vanity clustering. Real-volume reporting excludes the synthetic categories, so service rankings reflect actual demand instead of self-funded noise.

## 4-Axis Differentiation

1. **Wash filter** — 8-label buyer classification, cohort signal detection (uniform_amount, coordinated_start, uniform_tx_count, time_burst), strict + broad vanity clustering, conservative developer label.
2. **Free public data** — every label, every benchmark. Daily CC0 snapshots in [`printmoneylab/x402watch-data`](https://github.com/printmoneylab/x402watch-data).
3. **AI-native** — public REST API, x402-native paid endpoints, [llms.txt](https://x402.printmoneylab.com/llms.txt), [OpenAPI spec](https://api.x402.printmoneylab.com/openapi.json), [RSS](https://x402.printmoneylab.com/feed.xml), [/.well-known/x402](https://x402.printmoneylab.com/.well-known/x402), and an MCP server.
4. **Coverage** — 36,000+ services indexed across **Base, Solana, Polygon, and Arbitrum**.

## Quick Start

### Free API

```bash
curl https://api.x402.printmoneylab.com/api/v1/landing-stats
curl https://api.x402.printmoneylab.com/api/v1/categories
curl 'https://api.x402.printmoneylab.com/api/v1/services?search=ai'
```

Rate limit: 60 req/hour per IP. No API key. CC0-licensed.

### MCP server (one command)

```bash
smithery mcp add bakyang2/x402watch
```

Or add to any MCP client manually (Claude Desktop, Cursor, Cline):

```json
{
  "mcpServers": {
    "x402watch": {
      "transport": "streamable-http",
      "url": "https://api.x402.printmoneylab.com/mcp"
    }
  }
}
```

### Paid endpoint (x402)

```python
import asyncio, os
from eth_account import Account
from x402 import x402Client
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.http.clients.httpx import x402HttpxClient

async def main():
    acct = Account.from_key(os.environ["PRIVATE_KEY"])
    payer = x402Client()
    payer.register("eip155:8453", ExactEvmClientScheme(acct))
    async with x402HttpxClient(payer, base_url="https://api.x402.printmoneylab.com") as c:
        r = await c.post("/api/v1/wash/check", json={"address": "0x..."})
        print(r.json()["label"])

asyncio.run(main())
```

The 402 round-trip pays USDC on Base mainnet via the CDP facilitator, retries with the signed payment header, and returns 200 with the data — no signup, no API keys.

## API Endpoints

### Free (60 req/hour per IP)

| Endpoint | Description |
| --- | --- |
| `GET /api/v1/landing-stats` | Real-time market overview (services, transactions, real volume %) |
| `GET /api/v1/categories` | All 33 x402 service categories with stats |
| `GET /api/v1/categories/{slug}` | Category detail + 30-day time series + top services |
| `GET /api/v1/services` | Paginated service list with filters |
| `GET /api/v1/services/{id}` | Service detail: stats, time series, top buyers, label distribution |
| `GET /api/v1/trends` | 24-hour ecosystem trends |
| `GET /api/v1/wash-report` | Aggregate wash patterns + anonymized case studies |

### Paid (x402, USDC on Base)

| Endpoint | Price | Use case |
| --- | --- | --- |
| `GET /api/v1/services/{id}/wash-detail` | $0.005 | Operator audit — top 50 buyers + signal breakdown |
| `GET /api/v1/buyers/{address}/profile` | $0.005 | Wallet research |
| `GET /api/v1/services/{id}/transactions` | $0.01 | Custom analysis — raw 30-day transactions |
| `GET /api/v1/categories/{slug}/full-history` | $0.02 | Longitudinal research — 365-day hourly series |
| `POST /api/v1/wash/check` | $0.05 | Real-time wash analysis for any address |

Settled via the [Coinbase Developer Platform x402 facilitator](https://docs.cdp.coinbase.com/x402/welcome). Bazaar discovery extensions declared per route.

Full reference: [/api](https://x402.printmoneylab.com/api) · [Swagger UI](https://api.x402.printmoneylab.com/docs)

## MCP Tools

Listed on the [official MCP Registry](https://registry.modelcontextprotocol.io/v0/servers?search=printmoneylab) as `io.github.printmoneylab/x402watch`. Streamable-http at `https://api.x402.printmoneylab.com/mcp`. Five read-only tools:

| Tool | What it returns |
| --- | --- |
| `x402_get_categories` | All 33 categories with services count, 24h volume, real-volume %, label distribution |
| `x402_get_service` | One service's full record: stats, 30-day daily volume, top buyers, label mix |
| `x402_check_wash` | Aggregate wash-report dataset (per-address analysis is the paid `POST /wash/check` endpoint) |
| `x402_search_services` | Search 36k+ services with filters (category, chain, sort, page) |
| `x402_get_trends` | 24h trends: new services, hot services, category volume movers |

## Architecture

| Layer | Stack |
| --- | --- |
| Frontend | Next.js 16 (App Router) + Tailwind v4 + Recharts |
| Backend | FastAPI + PostgreSQL (TimescaleDB) + Redis (5-min cache) |
| Indexing | Bazaar discovery + EVM RPC (Alchemy) + Solana RPC (Helius) |
| Wash detection | NetworkX cohort signals, vanity clustering (strict + broad), single-buyer concentration analysis |
| AI classification | Claude Haiku 4.5 (per-service categorization), Claude Sonnet 4.5 (cross-validation) |
| Payments | x402 SDK 2.8.0, CDP facilitator on Base mainnet (USDC) |
| MCP server | FastMCP 3.x, streamable-http transport |
| Hosting | Oracle ARM (backend, free tier) + Vercel (frontend) + Cloudflare DNS |

## Methodology

Open, version-controlled, deterministic from public on-chain data:

→ **<https://x402.printmoneylab.com/docs/methodology>**

Covers 8-label priority order, cohort signal thresholds, vanity-cluster math, and the conservative developer label. Source markdown lives in [`content/methodology.md`](content/methodology.md).

## Resources

- 🌐 Site: <https://x402.printmoneylab.com>
- 📡 API: <https://api.x402.printmoneylab.com/api/v1> · [Swagger](https://api.x402.printmoneylab.com/docs)
- 🤖 MCP: `https://api.x402.printmoneylab.com/mcp`
- 📦 Open dataset: [`printmoneylab/x402watch-data`](https://github.com/printmoneylab/x402watch-data)
- 🤝 [Smithery](https://smithery.ai/servers/bakyang2/x402watch) · [MCP Registry](https://registry.modelcontextprotocol.io) · [Glama](https://glama.ai/mcp/servers/printmoneylab/x402watch)
- 🐦 Twitter: [@printmoneylab](https://twitter.com/printmoneylab)

## Repository Layout

This repo holds the public Next.js site under `src/`. The methodology markdown lives in [`content/methodology.md`](content/methodology.md) and is rendered at [/docs/methodology](https://x402.printmoneylab.com/docs/methodology). The FastAPI backend and indexers live on a separate Oracle host.

## Contributing

Pull requests welcome. For methodology questions, dispute a label, or report a misclassified service, please open a [GitHub Issue](https://github.com/printmoneylab/x402watch/issues) — labels are deterministic and reproducible from public on-chain data, so we'll walk through the signals that triggered the classification.

## License

- **Code**: Apache 2.0 (see [LICENSE](LICENSE))
- **Data**: CC0 (public domain), published daily to [`x402watch-data`](https://github.com/printmoneylab/x402watch-data)

## Status

Phase 1 MVP — actively developed. 9 systemd services running on the Oracle backend (api, mcp, 7 indexer/labeller/stats jobs). Daily snapshots commit to the data repo at 04:00 UTC.

---

Built by [PrintMoneyLab](https://printmoneylab.com).
