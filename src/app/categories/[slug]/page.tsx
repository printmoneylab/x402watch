import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import {
  fetchCategoryDetail,
  prettyCategory,
} from "@/lib/categories";
import {
  VolumeTimeSeries,
  LabelDonut,
  PriceHistogram,
} from "@/components/categories/DetailCharts";
import { TopServicesTable } from "@/components/categories/TopServicesTable";
import { JsonLd } from "@/components/common/JsonLd";
import { datasetSchema, SITE_URL, API_BASE } from "@/lib/jsonld";

// Edge runtime + dynamic rendering on Cloudflare Pages — no
// generateStaticParams (Pages can't precompute the full set on edge,
// and the backend's 5-min Redis cache absorbs the per-request cost).
export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  try {
    const detail = await fetchCategoryDetail(slug);
    if (!detail) return { title: "Category not found — x402watch" };
    const n = detail.stats.services_count;
    const vol = detail.stats.volume_24h;
    return {
      title: `${prettyCategory(detail.category)} on x402 — x402watch`,
      description: `${prettyCategory(detail.category)} services on x402: ${n.toLocaleString()} services, $${vol.toFixed(2)} 24h volume, ${detail.stats.real_volume_pct.toFixed(0)}% real demand.`,
    };
  } catch {
    return { title: "Category — x402watch" };
  }
}

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

export default async function CategoryDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const detail = await fetchCategoryDetail(slug);
  if (!detail) notFound();
  const s = detail.stats;

  const slugSafe = encodeURIComponent(detail.category);
  return (
    <main className="flex-1">
      <JsonLd
        data={datasetSchema({
          name: `x402 category: ${prettyCategory(detail.category)}`,
          description: `${s.services_count} ${prettyCategory(detail.category)} services on x402 — ${s.real_volume_pct.toFixed(0)}% real volume, ${s.tx_24h.toLocaleString()} transactions in the last 24h.`,
          url: `${SITE_URL}/categories/${slugSafe}`,
          apiUrl: `${API_BASE}/categories/${slugSafe}`,
          dateModified: s.last_hour ?? undefined,
        })}
      />
      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-6xl px-6 pt-10 pb-8 sm:pt-14 sm:pb-10">
          <Link
            href="/categories"
            className="inline-flex items-center gap-1 text-sm text-foreground/60 hover:text-foreground mb-4"
          >
            <ChevronLeft className="size-4" /> All categories
          </Link>
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-balance max-w-[24ch]">
            {prettyCategory(detail.category)}
          </h1>
          <p className="mt-3 font-mono text-xs text-foreground/45">
            {detail.category}
          </p>
          <dl className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-y-6 gap-x-6">
            {[
              { label: "services", value: fmtInt(s.services_count) },
              { label: "24h volume", value: fmtUsd(s.volume_24h) },
              { label: "24h transactions", value: fmtInt(s.tx_24h) },
              {
                label: "real volume",
                value: `${s.real_volume_pct.toFixed(1)}%`,
                accent: "text-emerald-400",
              },
            ].map((it) => (
              <div key={it.label} className="flex flex-col gap-1">
                <dt className="order-2 text-[11px] uppercase tracking-wide text-foreground/55">
                  {it.label}
                </dt>
                <dd
                  className={`order-1 font-mono text-2xl sm:text-3xl font-medium tracking-tight ${it.accent ?? ""}`}
                >
                  {it.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:py-14">
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="lg:col-span-2">
              <VolumeTimeSeries data={detail.time_series} />
            </div>
            <LabelDonut data={detail.label_distribution} />
            <PriceHistogram data={detail.price_distribution} />
          </div>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:py-14">
          <div className="flex items-end justify-between mb-6">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
              Top services
            </h2>
            <p className="text-xs text-foreground/50">
              Ranked by 30-day transaction count.
            </p>
          </div>
          <TopServicesTable services={detail.top_services} />
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:py-12 text-sm text-foreground/55">
          How are these labels calculated?{" "}
          <Link
            href="/docs/methodology"
            className="text-foreground/80 hover:text-foreground underline underline-offset-2"
          >
            Read the methodology →
          </Link>
        </div>
      </section>
    </main>
  );
}
