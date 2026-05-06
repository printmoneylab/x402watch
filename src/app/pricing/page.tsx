import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check, Sparkles } from "lucide-react";
import { WaitlistForm } from "@/components/pricing/WaitlistForm";
import { JsonLd } from "@/components/common/JsonLd";
import { datasetSchema, SITE_URL } from "@/lib/jsonld";

export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Pricing — x402watch",
  description:
    "Free public data + per-call x402 micropayments. Pro tier coming soon for service operators.",
};

const FREE_FEATURES = [
  "All 7 free endpoints (categories, services, trends, wash report)",
  "60 req/hour per IP — no API key, no signup",
  "MCP server with 5 read-only tools",
  "OpenAPI, llms.txt, RSS, /.well-known/x402",
  "Daily CC0 dataset snapshots",
];

const PRO_FEATURES = [
  "Monitor your own service's traffic in real time",
  "Alerts on label changes, wash spikes, new buyer cohorts",
  "Higher rate limits + priority routing",
  "Custom wash detection on your endpoints",
  "Direct support channel",
];

export default function PricingPage() {
  return (
    <main className="flex-1">
      <JsonLd
        data={datasetSchema({
          name: "x402watch pricing",
          description:
            "Free public x402 ecosystem data with seven open endpoints, plus a wait-listed Pro tier for service operators.",
          url: `${SITE_URL}/pricing`,
        })}
      />

      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-5xl px-6 pt-12 pb-8 sm:pt-16 sm:pb-10">
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-balance max-w-[24ch]">
            Pricing
          </h1>
          <p className="mt-4 max-w-2xl text-foreground/65 text-balance">
            Free public data and per-call x402 micropayments. A Pro tier for
            service operators is on the way — early-access 50% off for the
            first wave of wait list signups.
          </p>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-5xl px-6 py-10 sm:py-14">
          <div className="grid gap-5 lg:grid-cols-2 items-stretch">
            {/* Free tier */}
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6 flex flex-col">
              <div className="flex items-baseline gap-2">
                <h2 className="text-xl font-semibold tracking-tight">Free</h2>
                <span className="inline-flex items-center rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide text-emerald-300">
                  live
                </span>
              </div>
              <p className="mt-2 text-sm text-foreground/55 leading-relaxed">
                Everything the public dashboard runs on. CC0 data, no signup,
                AI-friendly machine-readable surfaces.
              </p>
              <p className="mt-5 text-3xl sm:text-4xl font-mono font-medium tracking-tight">
                $0
              </p>
              <ul className="mt-5 space-y-2 text-sm text-foreground/80">
                {FREE_FEATURES.map((f) => (
                  <li key={f} className="flex gap-2">
                    <Check className="size-4 mt-0.5 text-emerald-400 shrink-0" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-6 flex flex-wrap gap-2">
                <Link
                  href="/api"
                  className="inline-flex items-center gap-1.5 h-10 px-4 rounded-md border border-foreground/20 bg-foreground/[0.06] text-sm font-medium text-foreground hover:bg-foreground/10 transition-colors"
                >
                  Get started — no signup
                  <ArrowRight className="size-4" />
                </Link>
                <Link
                  href="https://api.x402.printmoneylab.com/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 h-10 px-4 rounded-md text-sm text-foreground/70 hover:text-foreground transition-colors"
                >
                  Swagger UI
                </Link>
              </div>
              <p className="mt-auto pt-6 text-xs text-foreground/45">
                Per-call x402 endpoints (wash detail, full history, on-demand
                wash check) are also free of any signup — pay USDC on Base, get
                data in one HTTP round-trip. See <Link href="/api" className="underline underline-offset-2 hover:text-foreground">/api</Link> for prices.
              </p>
            </div>

            {/* Pro tier */}
            <div className="relative rounded-lg border border-accent/30 bg-gradient-to-br from-accent/[0.04] to-foreground/[0.02] p-6 flex flex-col">
              <div className="flex items-baseline gap-2">
                <h2 className="text-xl font-semibold tracking-tight">Pro</h2>
                <span className="inline-flex items-center rounded-full border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wide text-accent">
                  coming soon
                </span>
              </div>
              <p className="mt-2 text-sm text-foreground/65 leading-relaxed">
                Deeper insights for service operators. Monitor your own
                traffic, get real-time alerts, and run wash detection on your
                own endpoints.
              </p>

              <div className="mt-5 inline-flex items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-1.5 text-xs text-amber-200/85 self-start">
                <Sparkles className="size-3.5" />
                Early-access 50% off for first-wave signups
              </div>

              <ul className="mt-5 space-y-2 text-sm text-foreground/80">
                {PRO_FEATURES.map((f) => (
                  <li key={f} className="flex gap-2">
                    <Check className="size-4 mt-0.5 text-accent shrink-0" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              <div className="mt-6 rounded-md border border-foreground/15 bg-background/40 p-4">
                <h3 className="text-sm font-semibold tracking-tight mb-3">
                  Join the wait list
                </h3>
                <WaitlistForm />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-3xl px-6 py-10 sm:py-12">
          <h2 className="text-base font-semibold tracking-tight text-foreground/85 mb-3">
            FAQ
          </h2>
          <div className="space-y-4 text-sm">
            <details className="group rounded-md border border-foreground/10 bg-foreground/[0.02] p-4">
              <summary className="cursor-pointer list-none font-medium text-foreground/85 group-open:mb-2">
                Is the free tier really free?
              </summary>
              <p className="text-foreground/65 leading-relaxed">
                Yes. Public REST endpoints, the MCP server, the dashboard, and
                the daily dataset are all CC0 with no signup. The x402-native
                paid endpoints are pay-per-call USDC and require no account
                either — you settle the 402 with your wallet.
              </p>
            </details>
            <details className="group rounded-md border border-foreground/10 bg-foreground/[0.02] p-4">
              <summary className="cursor-pointer list-none font-medium text-foreground/85 group-open:mb-2">
                When does Pro launch?
              </summary>
              <p className="text-foreground/65 leading-relaxed">
                We&apos;re building toward Day 26 launch and prioritising what
                wait list signups actually ask for. Wait listers get an email
                with the launch date, the early-access pricing, and a private
                onboarding link before the public announcement.
              </p>
            </details>
            <details className="group rounded-md border border-foreground/10 bg-foreground/[0.02] p-4">
              <summary className="cursor-pointer list-none font-medium text-foreground/85 group-open:mb-2">
                What does early access include?
              </summary>
              <p className="text-foreground/65 leading-relaxed">
                Lifetime 50% off the public Pro price for first-wave signups
                (no member cap; window closes one week after Day 26 launch).
                Same feature set as later tiers, just locked in at the
                early-access rate.
              </p>
            </details>
            <details className="group rounded-md border border-foreground/10 bg-foreground/[0.02] p-4">
              <summary className="cursor-pointer list-none font-medium text-foreground/85 group-open:mb-2">
                Will the free tier shrink when Pro launches?
              </summary>
              <p className="text-foreground/65 leading-relaxed">
                No. Everything currently free stays free under CC0. Pro is
                strictly additional — operator-specific features that don&apos;t
                replace anything in the free tier.
              </p>
            </details>
          </div>
        </div>
      </section>
    </main>
  );
}
