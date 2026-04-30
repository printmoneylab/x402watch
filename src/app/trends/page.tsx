import type { Metadata } from "next";
import { fetchTrends, TRENDS_FALLBACK, type TrendsPayload } from "@/lib/trends";
import { SummaryStats } from "@/components/trends/SummaryStats";
import { DailyNewChart } from "@/components/trends/DailyNewChart";
import { CategoryMovers } from "@/components/trends/CategoryMovers";
import {
  HotServices,
  RecentNewServices,
} from "@/components/trends/HotServices";
import { JsonLd } from "@/components/common/JsonLd";
import { datasetSchema, SITE_URL, API_BASE } from "@/lib/jsonld";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Trends — x402watch",
  description:
    "What's moving on x402 in the last 24 hours: new services, category volume movers, and surging activity.",
};

export default async function TrendsPage() {
  let payload: TrendsPayload = TRENDS_FALLBACK;
  try {
    payload = await fetchTrends();
  } catch (err) {
    console.error("[trends] live fetch failed, using fallback:", err);
  }

  const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

  return (
    <main className="flex-1">
      <JsonLd
        data={datasetSchema({
          name: "x402 trends — last 24 hours",
          description: `Daily x402 ecosystem snapshot: ${payload.summary.new_services_24h} new services, ${payload.summary.total_tx_24h.toLocaleString()} transactions, category volume movers, and surging-activity services.`,
          url: `${SITE_URL}/trends`,
          apiUrl: `${API_BASE}/trends`,
        })}
      />
      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-7xl px-6 pt-12 pb-8 sm:pt-16 sm:pb-10">
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-balance max-w-[24ch]">
            Trends
          </h1>
          <p className="mt-4 max-w-2xl text-foreground/65 text-balance">
            What&apos;s moving on x402 in the last 24 hours — new services,
            category volume movers, and activity surges across the network.
          </p>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-12">
          <SummaryStats summary={payload.summary} />
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-14">
          <div className="flex items-end justify-between mb-6">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
              Daily new services
            </h2>
            <p className="text-xs text-foreground/50 hidden sm:block">
              Indexed at first_seen, last 14 days.
            </p>
          </div>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,260px)_1fr] items-stretch">
            <div className="flex flex-col justify-center rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6">
              <p className="text-[11px] uppercase tracking-wide text-foreground/55">
                New services in last 24h
              </p>
              <p className="mt-1 font-mono text-4xl sm:text-5xl font-medium tracking-tight">
                {fmtInt(payload.summary.new_services_24h)}
              </p>
              <p className="mt-2 text-xs text-foreground/45">
                vs {fmtInt(payload.summary.new_services_prev_24h)} the previous
                24h.
              </p>
            </div>
            <DailyNewChart data={payload.daily_new_services} />
          </div>

          <div className="mt-8">
            <h3 className="text-base font-semibold tracking-tight mb-3">
              Recent new services (top 10)
            </h3>
            <RecentNewServices rows={payload.recent_new_services} />
          </div>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-14">
          <div className="flex items-end justify-between mb-6">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
              Volume movers (categories)
            </h2>
            <p className="text-xs text-foreground/50 hidden sm:block">
              24h vs previous 24h. Click a header to re-sort.
            </p>
          </div>
          <CategoryMovers rows={payload.category_movers} />
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-14">
          <div className="flex items-end justify-between mb-6">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
              Hot services
            </h2>
            <p className="text-xs text-foreground/50 hidden sm:block">
              ≥100 tx in 24h with ≥+50% surge vs previous 24h.
            </p>
          </div>
          <HotServices rows={payload.hot_services} />
        </div>
      </section>
    </main>
  );
}
