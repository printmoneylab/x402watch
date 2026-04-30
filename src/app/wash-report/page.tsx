import type { Metadata } from "next";
import {
  fetchWashReport,
  WASH_FALLBACK,
  type WashReportPayload,
} from "@/lib/wash";
import {
  WashStatsRow,
  WashTimeSeriesChart,
} from "@/components/wash/WashOverview";
import { LabelDistribution } from "@/components/wash/LabelDistribution";
import { CaseStudyCard } from "@/components/wash/CaseStudyCard";
import {
  MethodologyCTA,
  OperatorBox,
} from "@/components/wash/MethodologyCTA";
import { RelativeTime } from "@/components/common/RelativeTime";
import { JsonLd } from "@/components/common/JsonLd";
import {
  datasetSchema,
  articleSchema,
  SITE_URL,
  API_BASE,
} from "@/lib/jsonld";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Wash Report — x402watch",
  description:
    "Open methodology, anonymized findings on suspected wash, self-test, and developer traffic across x402. Updated daily.",
};

export default async function WashReportPage() {
  let payload: WashReportPayload = WASH_FALLBACK;
  try {
    payload = await fetchWashReport();
  } catch (err) {
    console.error("[wash-report] live fetch failed, using fallback:", err);
  }

  const updatedIso = payload.stats.last_updated || new Date().toISOString();
  return (
    <main className="flex-1">
      <JsonLd
        data={[
          articleSchema({
            headline: "x402 Wash Report — open methodology, anonymized findings",
            description:
              "Aggregate wash detection across the x402 ecosystem: 8-label classification, 30-day trends, anonymized case studies. Updated daily.",
            url: `${SITE_URL}/wash-report`,
            datePublished: updatedIso,
            dateModified: updatedIso,
          }),
          datasetSchema({
            name: "x402 wash report dataset",
            description: `Buyer-level label distribution and wash-percentage time series across the x402 ecosystem (${payload.stats.total_active_buyers_30d.toLocaleString()} active buyers, last 30 days).`,
            url: `${SITE_URL}/wash-report`,
            apiUrl: `${API_BASE}/wash-report`,
            dateModified: updatedIso,
          }),
        ]}
      />
      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-7xl px-6 pt-12 pb-8 sm:pt-16 sm:pb-10">
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-balance max-w-[24ch]">
            Wash Report
          </h1>
          <p className="mt-4 max-w-2xl text-foreground/65 text-balance">
            Open methodology, anonymized findings. Updated daily.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
            <RelativeTime
              iso={payload.stats.last_updated}
              className="inline-flex items-center rounded-full border border-foreground/15 bg-foreground/[0.04] px-2 py-1 font-mono text-foreground/70"
            />
          </div>
          <p className="mt-6 max-w-3xl text-sm text-foreground/55 italic leading-relaxed">
            Most x402 dashboards count transactions. We classify them.
          </p>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-12">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-6">
            Total wash overview
          </h2>
          <WashStatsRow stats={payload.stats} />
          <div className="mt-8">
            <WashTimeSeriesChart data={payload.wash_pct_time_series} />
          </div>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            Pattern types
          </h2>
          <p className="text-sm text-foreground/55 mb-6 max-w-2xl">
            Every active buyer (30-day window) carries one of eight labels,
            applied in priority order. Labels are stable signals — not
            judgments — and reproducible from public on-chain data.
          </p>
          <LabelDistribution distribution={payload.label_distribution} />
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-14">
          <h2 className="text-xl sm:text-2xl font-semibold tracking-tight mb-2">
            Anonymized case studies
          </h2>
          <p className="text-sm text-foreground/55 mb-6 max-w-2xl">
            Real patterns observed in the network — service names and seller
            addresses redacted. Operators may recognize their own footprint;
            others should treat this as a methodology preview.
          </p>
          {payload.case_studies.length === 0 ? (
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-12 text-center text-sm text-foreground/55">
              Case studies refreshing — check back shortly.
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {payload.case_studies.map((cs) => (
                <CaseStudyCard key={cs.anonymous_id} study={cs} />
              ))}
            </div>
          )}
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-14">
          <MethodologyCTA />
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-12">
          <h2 className="text-base font-semibold tracking-tight text-foreground/85 mb-3">
            For operators
          </h2>
          <OperatorBox />
        </div>
      </section>
    </main>
  );
}
