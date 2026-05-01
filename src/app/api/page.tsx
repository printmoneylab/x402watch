import type { Metadata } from "next";
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { CodeBlock } from "@/components/api/CodeBlock";
import { PaidEndpointCard } from "@/components/api/PaidEndpointCard";
import { FREE_ENDPOINTS, PAID_ENDPOINTS } from "@/lib/api-endpoints";
import { JsonLd } from "@/components/common/JsonLd";
import { datasetSchema, SITE_URL } from "@/lib/jsonld";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "API — x402watch",
  description:
    "Free public x402 ecosystem data + per-call x402 micropayments. No signup. AI-native.",
};

const fmtPrice = (p: number) => `$${p.toFixed(p < 0.01 ? 3 : 2)}`;

export default function ApiPage() {
  return (
    <main className="flex-1">
      <JsonLd
        data={datasetSchema({
          name: "x402watch API",
          description:
            "Free public x402 ecosystem data with seven open endpoints plus five x402-native paid endpoints for deeper analysis.",
          url: `${SITE_URL}/api`,
          apiUrl: "https://api.x402.printmoneylab.com/api/v1",
        })}
      />

      {/* Hero */}
      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-5xl px-6 pt-12 pb-8 sm:pt-16 sm:pb-10">
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-balance max-w-[24ch]">
            API
          </h1>
          <p className="mt-4 max-w-2xl text-foreground/65 text-balance">
            Free public data plus x402 micropayments for deeper queries. No
            signup, no rate limits behind a paywall.
          </p>
          <div className="mt-5 flex flex-wrap gap-3 text-xs">
            <Link
              href="https://api.x402.printmoneylab.com/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-foreground/15 bg-foreground/[0.04] px-3 py-1.5 text-foreground/75 hover:text-foreground hover:bg-foreground/10"
            >
              Swagger UI <ExternalLink className="size-3" />
            </Link>
            <Link
              href="https://api.x402.printmoneylab.com/openapi.json"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-foreground/15 bg-foreground/[0.04] px-3 py-1.5 text-foreground/75 hover:text-foreground hover:bg-foreground/10"
            >
              OpenAPI spec <ExternalLink className="size-3" />
            </Link>
            <Link
              href="/llms.txt"
              className="inline-flex items-center gap-1 rounded-md border border-foreground/15 bg-foreground/[0.04] px-3 py-1.5 text-foreground/75 hover:text-foreground hover:bg-foreground/10"
            >
              llms.txt
            </Link>
          </div>
        </div>
      </section>

      {/* Quick Start */}
      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            Quick start
          </h2>
          <p className="text-sm text-foreground/55 mb-6 max-w-2xl">
            Every free endpoint returns plain JSON. No headers, no auth.
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            <CodeBlock lang="bash">
{`curl https://api.x402.printmoneylab.com/api/v1/landing-stats`}
            </CodeBlock>
            <CodeBlock lang="python">
{`import requests
r = requests.get(
    "https://api.x402.printmoneylab.com/api/v1/categories"
)
print(r.json()["total_categories"])  # 33`}
            </CodeBlock>
          </div>
          <div className="mt-4">
            <p className="text-[11px] uppercase tracking-wide text-foreground/45 mb-1.5">
              Sample response (landing-stats)
            </p>
            <CodeBlock lang="json">
{`{
  "stats": {
    "services_indexed": 36412,
    "transactions_analyzed": 1842993,
    "active_buyers": 2045,
    "real_volume_pct": 80.2,
    "last_updated": "2026-05-01T00:14:00Z"
  },
  "label_distribution": [...],
  "category_volume_series": [...],
  "daily_new_services": [...]
}`}
            </CodeBlock>
          </div>
        </div>
      </section>

      {/* Free endpoints */}
      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            Free endpoints
          </h2>
          <p className="text-sm text-foreground/55 mb-6 max-w-2xl">
            Open to everyone, including AI agents. 60 requests per hour per
            IP. CC0-licensed, attribution appreciated.
          </p>
          <div className="overflow-x-auto rounded-lg border border-foreground/10">
            <table className="w-full text-sm">
              <thead className="bg-foreground/[0.04] text-foreground/70">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Endpoint</th>
                  <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">
                    Description
                  </th>
                  <th className="text-right px-3 py-2 font-medium">Rate limit</th>
                </tr>
              </thead>
              <tbody>
                {FREE_ENDPOINTS.map((e) => (
                  <tr
                    key={e.path}
                    className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
                  >
                    <td className="px-3 py-2">
                      <code className="font-mono text-xs sm:text-sm text-foreground/85">
                        {e.path}
                      </code>
                      <p className="mt-1 text-xs text-foreground/55 sm:hidden">
                        {e.description}
                      </p>
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell text-foreground/65">
                      {e.description}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-foreground/55">
                      {e.rateLimit}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Pay-per-Call */}
      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            Pay-per-call (x402)
          </h2>
          <p className="text-sm text-foreground/65 max-w-3xl leading-relaxed">
            x402 is HTTP 402 Payment Required, brought back. The endpoints
            below return 402 with payment instructions. Pay USDC on Base or
            Solana, retry, get data. No signup. AI agents do this
            automatically — see the Quick start below.
          </p>
          <Link
            href="https://x402.org"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 inline-flex items-center gap-1 text-sm text-accent hover:underline"
          >
            Learn x402 <ExternalLink className="size-3.5" />
          </Link>

          <div className="mt-6 overflow-x-auto rounded-lg border border-foreground/10">
            <table className="w-full text-sm">
              <thead className="bg-foreground/[0.04] text-foreground/70">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">Endpoint</th>
                  <th className="text-right px-3 py-2 font-medium">Price</th>
                  <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">
                    Use case
                  </th>
                </tr>
              </thead>
              <tbody>
                {PAID_ENDPOINTS.map((e) => (
                  <tr
                    key={e.path}
                    className="border-t border-foreground/5 hover:bg-foreground/[0.03]"
                  >
                    <td className="px-3 py-2">
                      <span className="inline-flex items-center gap-2">
                        <span
                          className={
                            e.method === "GET"
                              ? "inline-flex items-center justify-center min-w-10 h-5 rounded text-[10px] font-mono uppercase border border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                              : "inline-flex items-center justify-center min-w-10 h-5 rounded text-[10px] font-mono uppercase border border-amber-500/40 bg-amber-500/10 text-amber-300"
                          }
                        >
                          {e.method}
                        </span>
                        <code className="font-mono text-xs sm:text-sm text-foreground/85">
                          {e.path}
                        </code>
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">
                      {fmtPrice(e.priceUsd)}
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell text-foreground/65">
                      {e.useCase}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-6 space-y-3">
            <h3 className="text-sm font-semibold tracking-tight text-foreground/80">
              Endpoint details
            </h3>
            {PAID_ENDPOINTS.map((e) => (
              <PaidEndpointCard key={e.path} ep={e} />
            ))}
          </div>
        </div>
      </section>

      {/* x402 Quick Start (with code) */}
      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            x402 quick start
          </h2>
          <p className="text-sm text-foreground/55 mb-6 max-w-2xl">
            The full pay-and-fetch flow in three forms.
          </p>

          <div className="space-y-5">
            <div>
              <p className="text-[11px] uppercase tracking-wide text-foreground/45 mb-1.5">
                1. The raw flow (curl + manual)
              </p>
              <CodeBlock lang="bash">
{`# Step 1: hit the endpoint without payment.
curl -X POST https://api.x402.printmoneylab.com/api/v1/wash/check \\
  -H "Content-Type: application/json" \\
  -d '{"address": "0x29b...725"}'

# → 402 Payment Required
# Body lists the accepted networks, payTo addresses, and amounts.

# Step 2: pay USDC, build the X-PAYMENT header (base64 EIP-3009 sig
# for Base / signed transfer for Solana). The x402 SDK does this for
# you — see below.

# Step 3: retry with the payment header.
curl -X POST https://api.x402.printmoneylab.com/api/v1/wash/check \\
  -H "Content-Type: application/json" \\
  -H "X-PAYMENT: <base64 payload>" \\
  -d '{"address": "0x29b...725"}'

# → 200 OK + JSON body`}
              </CodeBlock>
            </div>

            <div>
              <p className="text-[11px] uppercase tracking-wide text-foreground/45 mb-1.5">
                2. JavaScript / TypeScript (x402-axios)
              </p>
              <CodeBlock lang="typescript">
{`import axios from "axios";
import { withPayment } from "x402-axios";
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";

const wallet = createWalletClient({
  account: privateKeyToAccount(process.env.PRIVATE_KEY!),
  chain: base,
  transport: http(),
});

const client = withPayment(axios.create(), { wallet });

const r = await client.post(
  "https://api.x402.printmoneylab.com/api/v1/wash/check",
  { address: "0x29b...725" }
);
console.log(r.data.label, r.data.confidence);`}
              </CodeBlock>
            </div>

            <div>
              <p className="text-[11px] uppercase tracking-wide text-foreground/45 mb-1.5">
                3. Python (x402-httpx)
              </p>
              <CodeBlock lang="python">
{`import httpx
from x402.clients.httpx import x402HttpxClient
from eth_account import Account

acct = Account.from_key(os.environ["PRIVATE_KEY"])

async with x402HttpxClient(account=acct, base_url="https://api.x402.printmoneylab.com") as client:
    r = await client.post(
        "/api/v1/wash/check",
        json={"address": "0x29b...725"},
    )
    print(r.json()["label"])`}
              </CodeBlock>
            </div>
          </div>
        </div>
      </section>

      {/* Networks */}
      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            Networks
          </h2>
          <p className="text-sm text-foreground/55 mb-6 max-w-2xl">
            Pay USDC on either of two settlement chains. The 402 response
            lists the active payTo addresses; clients pick the cheapest.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-5">
              <p className="text-[11px] uppercase tracking-wide text-foreground/55">
                Base
              </p>
              <p className="mt-1 font-mono text-foreground/85">USDC native</p>
              <p className="mt-3 text-xs text-foreground/55">
                Lowest fees. Confirmation in ~1s. EIP-3009 signed transfer.
              </p>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-5">
              <p className="text-[11px] uppercase tracking-wide text-foreground/55">
                Solana
              </p>
              <p className="mt-1 font-mono text-foreground/85">USDC SPL</p>
              <p className="mt-3 text-xs text-foreground/55">
                Sub-second finality. SPL Token signed transfer.
              </p>
            </div>
          </div>
          <p className="mt-4 text-xs text-foreground/45">
            Settlement is finalized via the Coinbase Developer Platform x402
            facilitator.
          </p>
        </div>
      </section>

      {/* For AI Agents */}
      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            For AI agents
          </h2>
          <p className="text-sm text-foreground/65 max-w-3xl leading-relaxed">
            This API is built for autonomous agents. Every paid endpoint is
            x402-native — your agent pays and receives data in a single HTTP
            round-trip, no API keys to rotate.
          </p>
          <ul className="mt-5 space-y-2 text-sm">
            <li className="flex gap-2">
              <span className="text-foreground/40 font-mono">·</span>
              <Link
                href="/llms.txt"
                className="text-foreground/85 hover:text-foreground underline underline-offset-2"
              >
                /llms.txt
              </Link>
              <span className="text-foreground/55">— discovery hint</span>
            </li>
            <li className="flex gap-2">
              <span className="text-foreground/40 font-mono">·</span>
              <Link
                href="https://api.x402.printmoneylab.com/openapi.json"
                target="_blank"
                rel="noopener noreferrer"
                className="text-foreground/85 hover:text-foreground underline underline-offset-2"
              >
                /openapi.json
              </Link>
              <span className="text-foreground/55">— full machine-readable spec</span>
            </li>
            <li className="flex gap-2">
              <span className="text-foreground/40 font-mono">·</span>
              <Link
                href="/.well-known/x402"
                className="text-foreground/85 hover:text-foreground underline underline-offset-2"
              >
                /.well-known/x402
              </Link>
              <span className="text-foreground/55">— x402 service manifest</span>
            </li>
            <li className="flex gap-2">
              <span className="text-foreground/40 font-mono">·</span>
              <Link
                href="/feed.xml"
                className="text-foreground/85 hover:text-foreground underline underline-offset-2"
              >
                /feed.xml
              </Link>
              <span className="text-foreground/55">— RSS of recent ecosystem changes</span>
            </li>
            <li className="flex gap-2">
              <span className="text-foreground/40 font-mono">·</span>
              <span className="font-mono text-foreground/55">MCP server</span>
              <span className="text-foreground/45">— rolling out (Phase 1)</span>
            </li>
          </ul>
        </div>
      </section>

      {/* SLA + Limits */}
      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            SLA &amp; limits
          </h2>
          <dl className="mt-5 grid gap-4 sm:grid-cols-2 text-sm">
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-4">
              <dt className="text-foreground/55 text-xs uppercase tracking-wide">Free tier</dt>
              <dd className="mt-1 text-foreground/85">60 req/hour per IP</dd>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-4">
              <dt className="text-foreground/55 text-xs uppercase tracking-wide">Paid tier</dt>
              <dd className="mt-1 text-foreground/85">No rate limit per address (within reason)</dd>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-4">
              <dt className="text-foreground/55 text-xs uppercase tracking-wide">Cache</dt>
              <dd className="mt-1 text-foreground/85">5 minutes on most endpoints</dd>
            </div>
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-4">
              <dt className="text-foreground/55 text-xs uppercase tracking-wide">Uptime target</dt>
              <dd className="mt-1 text-foreground/85">99% (free-tier infra)</dd>
            </div>
          </dl>
          <p className="mt-5 text-sm text-foreground/55">
            Issues / questions:{" "}
            <Link
              href="https://github.com/printmoneylab/x402watch/issues"
              target="_blank"
              rel="noopener noreferrer"
              className="text-foreground/85 hover:text-foreground underline underline-offset-2"
            >
              GitHub Issues
            </Link>
            .
          </p>
        </div>
      </section>
    </main>
  );
}
