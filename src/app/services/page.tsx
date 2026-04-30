import type { Metadata } from "next";
import { Suspense } from "react";
import { ServicesView } from "@/components/services/ServicesView";
import {
  fetchServices,
  isPerPage,
  type ServiceListPayload,
  type ServiceFilters,
  type SortKey,
  SORT_KEYS,
} from "@/lib/services";
import { fetchCategories } from "@/lib/categories";
import { JsonLd } from "@/components/common/JsonLd";
import { datasetSchema, SITE_URL, API_BASE } from "@/lib/jsonld";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Services — x402watch",
  description:
    "x402 services indexed across all chains, with filters, real-vs-wash split, and live volume.",
};

const FALLBACK: ServiceListPayload = {
  services: [],
  pagination: { page: 1, page_size: 50, total: 0, total_pages: 0 },
  summary: { total_volume_24h: 0, total_tx_24h: 0 },
  filters_applied: {},
};

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K` : `$${n.toFixed(2)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

function paramsToFilters(sp: Record<string, string | string[] | undefined>): ServiceFilters {
  const get = (k: string): string | undefined => {
    const v = sp[k];
    if (Array.isArray(v)) return v[0];
    return v;
  };
  const sort = get("sort");
  const order = get("order");
  const perPageRaw = get("per_page") ? parseInt(get("per_page")!, 10) : undefined;
  return {
    search: get("search") || undefined,
    category: get("category") || undefined,
    chain: get("chain") || undefined,
    price_bucket: get("price_bucket") || undefined,
    min_real_pct: get("min_real_pct") ? Number(get("min_real_pct")) : undefined,
    max_wash_pct: get("max_wash_pct") ? Number(get("max_wash_pct")) : undefined,
    active_only: get("active_only") === "true",
    show_placeholder: get("show_placeholder") === "true",
    sort: (SORT_KEYS as readonly string[]).includes(sort ?? "")
      ? (sort as SortKey)
      : undefined,
    order: order === "asc" || order === "desc" ? order : undefined,
    page: get("page") ? Math.max(1, parseInt(get("page")!, 10) || 1) : undefined,
    per_page: isPerPage(perPageRaw) ? perPageRaw : undefined,
  };
}

export default async function ServicesPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const filters = paramsToFilters(sp);

  let payload: ServiceListPayload = FALLBACK;
  try {
    payload = await fetchServices(filters);
  } catch (err) {
    console.error("[services] live fetch failed, using fallback:", err);
  }

  let categoryNames: string[] = [];
  try {
    const cats = await fetchCategories();
    categoryNames = cats.categories.map((c) => c.category).sort();
  } catch (err) {
    console.error("[services] categories fetch failed:", err);
  }

  return (
    <main className="flex-1">
      <JsonLd
        data={datasetSchema({
          name: "x402 services",
          description: `${payload.pagination.total.toLocaleString()} indexed x402 services across all chains, with filters, classification labels, and real-vs-wash splits.`,
          url: `${SITE_URL}/services`,
          apiUrl: `${API_BASE}/services`,
        })}
      />
      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-7xl px-6 pt-12 pb-8 sm:pt-16 sm:pb-10">
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-balance max-w-[24ch]">
            Services
          </h1>
          <p className="mt-4 max-w-2xl text-foreground/65 text-balance">
            {fmtInt(payload.pagination.total)} x402 services indexed across{" "}
            {filters.chain ? `${filters.chain}` : "all chains"} — with live
            filters, classification labels, and real-vs-wash splits.
          </p>
          {!filters.show_placeholder && (
            <p className="mt-2 text-xs text-foreground/45">
              <span className="font-mono">premium_placeholder</span> services hidden by default —
              toggle below to show them.
            </p>
          )}
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-7xl px-6 py-10 sm:py-12">
          <Suspense
            fallback={
              <div className="h-9 w-full max-w-md rounded-md bg-foreground/5 animate-pulse" />
            }
          >
            <ServicesView initialPayload={payload} categories={categoryNames} />
          </Suspense>
        </div>
      </section>
    </main>
  );
}
