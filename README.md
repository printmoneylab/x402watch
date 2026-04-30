# x402watch

> Wash-filtered intelligence layer for the x402 ecosystem.

[![Live](https://img.shields.io/badge/live-x402.printmoneylab.com-3ee0a3)](https://x402.printmoneylab.com)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Data: CC0](https://img.shields.io/badge/data-CC0-lightgrey)](https://github.com/printmoneylab/x402watch-data)

x402watch indexes 36,000+ x402 services across Base, Solana, Polygon, and
Arbitrum, classifies them with AI, and detects wash trading patterns using
cohort signal analysis. All data is published daily under CC0.

## 4-Axis Differentiation

1. **Wash Filter** — 8-label classification + cohort signal detection
2. **Free Public Data** — every label, every benchmark
3. **Time-Series Asset** — daily snapshots committed to GitHub
4. **AI-Native** — public API, MCP server (Day 21), llms.txt

## Live

- Site: <https://x402.printmoneylab.com>
- API: <https://api.x402.printmoneylab.com/api/v1>
- API docs: <https://api.x402.printmoneylab.com/docs>
- Data: <https://github.com/printmoneylab/x402watch-data>
- Methodology: <https://x402.printmoneylab.com/docs/methodology>

## Tech Stack

- **Backend**: FastAPI + PostgreSQL (TimescaleDB) + Redis
- **Frontend**: Next.js 16 + Tailwind v4 + Recharts
- **Indexing**: Helius (Solana), public RPC (Base/Arbitrum)
- **AI**: Claude Haiku 4.5 (categorization), Claude Sonnet 4.5 (validation)
- **Hosting**: Oracle ARM (free tier) + Vercel + Cloudflare

## Repository Layout

This repo holds the public Next.js site under `src/`. The methodology
markdown lives in [`content/methodology.md`](content/methodology.md) and
is rendered at [/docs/methodology](https://x402.printmoneylab.com/docs/methodology).
The FastAPI backend and indexers live on a separate Oracle host.

## License

- **Code**: Apache 2.0 (see [LICENSE](LICENSE))
- **Data**: CC0 (public domain), published daily to
  [`x402watch-data`](https://github.com/printmoneylab/x402watch-data)

## Status

Phase 1 MVP — under active development. Issue templates and contribution
guidelines coming as the project stabilizes.

---

Built by [PrintMoneyLab](https://printmoneylab.com).
