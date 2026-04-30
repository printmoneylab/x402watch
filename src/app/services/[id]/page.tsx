import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft, ExternalLink } from "lucide-react";
import { fetchServiceDetail } from "@/lib/services";
import { prettyCategory } from "@/lib/categories";
import {
  ServiceVolumeSeries,
  ServiceLabelDonut,
} from "@/components/services/DetailCharts";
import { TopBuyersTable } from "@/components/services/TopBuyersTable";
import { JsonLd } from "@/components/common/JsonLd";
import {
  serviceSchema,
  datasetSchema,
  SITE_URL,
  API_BASE,
} from "@/lib/jsonld";

export const revalidate = 300;
// Don't pre-render at build time — 36k services is too many.
export const dynamicParams = true;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const detail = await fetchServiceDetail(id);
    if (!detail) return { title: "Service not found — x402watch" };
    const name = detail.service.name?.slice(0, 80) ?? `service ${id}`;
    return {
      title: `${name} — x402watch`,
      description:
        detail.service.description?.slice(0, 200) ??
        `x402 service #${id}: category ${detail.service.category}, ${detail.stats.tx_total.toLocaleString()} total tx.`,
    };
  } catch {
    return { title: "Service — x402watch" };
  }
}

const fmtUsd = (n: number | null) =>
  n == null ? "—"
  : n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);
function shortAddr(a: string): string {
  if (!a) return "";
  if (a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

export default async function ServiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const detail = await fetchServiceDetail(id);
  if (!detail) notFound();

  const s = detail.service;
  const st = detail.stats;

  const detailUrl = `${SITE_URL}/services/${s.id}`;
  return (
    <main className="flex-1">
      <JsonLd
        data={[
          serviceSchema({
            id: s.id,
            name: s.name ?? `service ${s.id}`,
            description: s.description,
            category: s.category,
            priceUsd: s.price_amount,
            url: detailUrl,
          }),
          datasetSchema({
            name: `x402 service #${s.id}: time series and buyer labels`,
            description: `30-day daily volume, transaction counts, and buyer-label distribution for ${s.name ?? `service ${s.id}`}.`,
            url: detailUrl,
            apiUrl: `${API_BASE}/services/${s.id}`,
            dateModified: s.last_seen ?? undefined,
          }),
        ]}
      />
      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-6xl px-6 pt-10 pb-8 sm:pt-14 sm:pb-10">
          <Link
            href="/services"
            className="inline-flex items-center gap-1 text-sm text-foreground/60 hover:text-foreground mb-4"
          >
            <ChevronLeft className="size-4" /> All services
          </Link>

          <div className="flex flex-wrap items-center gap-2 mb-3">
            <Link
              href={`/categories/${encodeURIComponent(s.category)}`}
              className="inline-flex items-center rounded-full border border-foreground/15 bg-foreground/[0.04] px-2 py-0.5 text-[11px] font-mono text-foreground/75 hover:border-foreground/30"
            >
              {prettyCategory(s.category)}
            </Link>
            <span className="inline-flex items-center rounded-full border border-foreground/15 bg-foreground/[0.04] px-2 py-0.5 text-[11px] font-mono text-foreground/75">
              {s.chain}
            </span>
            <span className="font-mono text-[11px] text-foreground/45">#{s.id}</span>
          </div>

          <h1 className="text-2xl sm:text-4xl font-semibold tracking-tight text-balance max-w-[50ch]">
            {s.name || "(no name)"}
          </h1>
          {s.description && s.description !== s.name && (
            <p className="mt-3 max-w-3xl text-foreground/70 text-pretty">
              {s.description}
            </p>
          )}

          <div className="mt-5 flex flex-col sm:flex-row gap-3 sm:gap-6 text-xs text-foreground/55">
            <div>
              seller{" "}
              <span className="font-mono text-foreground/80" title={s.seller_address}>
                {shortAddr(s.seller_address)}
              </span>
            </div>
            {s.resource_url && (
              <Link
                href={s.resource_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-mono text-foreground/70 hover:text-foreground truncate max-w-md"
              >
                {s.resource_url}
                <ExternalLink className="size-3 shrink-0" />
              </Link>
            )}
            <div>price <span className="font-mono text-foreground/80">{fmtUsd(s.price_amount)}</span></div>
          </div>

          <dl className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-y-6 gap-x-6">
            {[
              { label: "total tx", value: fmtInt(st.tx_total) },
              { label: "24h tx", value: fmtInt(st.tx_24h) },
              { label: "24h volume", value: fmtUsd(st.volume_24h) },
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
          {(s.wash_pct > 0 || s.developer_volume_pct > 0) && (
            <p className="mt-4 text-xs text-foreground/55">
              {s.wash_pct > 0 && (
                <>
                  flagged: <span className="font-mono text-rose-400">
                    {s.wash_pct.toFixed(1)}% suspected wash
                  </span>
                  {" · "}
                </>
              )}
              {s.developer_volume_pct > 0 && (
                <>
                  <span className="font-mono text-orange-400">
                    {s.developer_volume_pct.toFixed(1)}% developer traffic
                  </span>
                </>
              )}
            </p>
          )}
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:py-14">
          <div className="grid gap-5 lg:grid-cols-2">
            <div className="lg:col-span-2">
              <ServiceVolumeSeries data={detail.time_series_30d} />
            </div>
            <ServiceLabelDonut data={detail.label_distribution} />
            <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6 text-sm text-foreground/65">
              <h3 className="text-base font-semibold tracking-tight text-foreground mb-3">
                What these labels mean
              </h3>
              <p className="text-foreground/65 leading-relaxed mb-3">
                Every buyer wallet gets one of 8 labels per day based on cohort,
                vanity, and timing signals. Real-volume reporting excludes
                self-test, suspected_wash, and developer traffic.
              </p>
              <Link
                href="https://github.com/printmoneylab/x402watch/blob/main/docs/wash-filter-methodology.md"
                target="_blank"
                rel="noopener noreferrer"
                className="text-foreground/85 hover:text-foreground inline-flex items-center gap-1 underline underline-offset-2"
              >
                Read the methodology <ExternalLink className="size-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:py-14">
          <div className="flex items-end justify-between mb-6">
            <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">
              Top buyers
            </h2>
            <p className="text-xs text-foreground/50">
              Ranked by transaction count.
            </p>
          </div>
          <TopBuyersTable buyers={detail.top_buyers} />
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:py-12 text-sm text-foreground/55">
          Are you the operator? See how to{" "}
          <Link
            href="https://github.com/printmoneylab/x402watch/issues/new"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground/80 hover:text-foreground underline underline-offset-2"
          >
            dispute a label
          </Link>
          .
        </div>
      </section>
    </main>
  );
}
