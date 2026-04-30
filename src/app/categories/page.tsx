import type { Metadata } from "next";
import { Suspense } from "react";
import { CategoriesView } from "@/components/categories/CategoriesView";
import { fetchCategories, type CategoryListPayload } from "@/lib/categories";

export const revalidate = 300;

export const metadata: Metadata = {
  title: "Categories — x402watch",
  description:
    "33 categories of x402 services, classified by AI and verified across two LLMs. Live volume, real-vs-wash split, free public data.",
};

const FALLBACK: CategoryListPayload = {
  categories: [],
  total_categories: 0,
  total_services: 0,
  total_volume_24h: 0,
  total_tx_24h: 0,
  last_updated: new Date().toISOString(),
};

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K` : `$${n.toFixed(2)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

export default async function CategoriesPage() {
  let payload: CategoryListPayload = FALLBACK;
  try {
    payload = await fetchCategories();
  } catch (err) {
    console.error("[categories] live fetch failed, using fallback:", err);
  }

  return (
    <main className="flex-1">
      <section className="border-b border-foreground/10">
        <div className="mx-auto max-w-6xl px-6 pt-12 pb-8 sm:pt-16 sm:pb-10">
          <h1 className="text-3xl sm:text-5xl font-semibold tracking-tight text-balance max-w-[24ch]">
            Categories
          </h1>
          <p className="mt-4 max-w-2xl text-foreground/65 text-pretty">
            {payload.total_categories} categories of x402 services. Click any category to
            drill in.
          </p>
          {/* Stats bar */}
          <dl className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-y-6 gap-x-6">
            {[
              { label: "categories", value: fmtInt(payload.total_categories) },
              { label: "services", value: fmtInt(payload.total_services) },
              { label: "24h volume", value: fmtUsd(payload.total_volume_24h) },
              { label: "24h transactions", value: fmtInt(payload.total_tx_24h) },
            ].map((it) => (
              <div key={it.label} className="flex flex-col gap-1">
                <dt className="order-2 text-[11px] uppercase tracking-wide text-foreground/55">
                  {it.label}
                </dt>
                <dd className="order-1 font-mono text-2xl sm:text-3xl font-medium tracking-tight">
                  {it.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section className="border-b border-foreground/5">
        <div className="mx-auto max-w-6xl px-6 py-10 sm:py-12">
          <Suspense
            fallback={
              <div className="h-9 w-64 rounded-md bg-foreground/5 animate-pulse" />
            }
          >
            <CategoriesView payload={payload} />
          </Suspense>
        </div>
      </section>
    </main>
  );
}
