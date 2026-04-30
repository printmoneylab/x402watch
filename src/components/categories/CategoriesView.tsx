"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useSearchParams, useRouter, usePathname } from "next/navigation";
import {
  LayoutGrid,
  Table as TableIcon,
  ArrowUpDown,
  ArrowDown,
  ArrowUp,
} from "lucide-react";
import { CategoryCard } from "./CategoryCard";
import { LabelMiniBar } from "./LabelMiniBar";
import {
  prettyCategory,
  type CategoryRow,
  type CategoryListPayload,
} from "@/lib/categories";
import { cn } from "@/lib/utils";

type View = "grid" | "table";
type SortKey = "volume_24h" | "services_count" | "avg_price" | "real_pct" | "alpha";
type Order = "asc" | "desc";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "volume_24h",     label: "24h Volume" },
  { key: "services_count", label: "Services count" },
  { key: "avg_price",      label: "Avg Price" },
  { key: "real_pct",       label: "Real Volume %" },
  { key: "alpha",          label: "Alphabetical" },
];

const VIEWS: View[] = ["grid", "table"];
const SORT_KEYS: SortKey[] = SORTS.map((s) => s.key);

const DEFAULT_VIEW: View = "grid";
const DEFAULT_SORT: SortKey = "volume_24h";
const DEFAULT_SEARCH = "";

const DEFAULT_ORDER_FOR_SORT: Record<SortKey, Order> = {
  volume_24h: "desc",
  services_count: "desc",
  avg_price: "desc",
  real_pct: "desc",
  alpha: "asc",
};

function getSortValue(row: CategoryRow, key: SortKey): number | string {
  switch (key) {
    case "volume_24h":     return row.volume_24h;
    case "services_count": return row.services_count;
    case "avg_price":      return row.avg_price ?? -Infinity;
    case "real_pct":       return row.real_volume_pct;
    case "alpha":          return row.category;
  }
}

function sortRows(rows: CategoryRow[], key: SortKey, order: Order): CategoryRow[] {
  const dir = order === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = getSortValue(a, key);
    const vb = getSortValue(b, key);
    if (typeof va === "string" && typeof vb === "string") {
      return va.localeCompare(vb) * dir;
    }
    return ((va as number) - (vb as number)) * dir;
  });
}

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

export function CategoriesView({ payload }: { payload: CategoryListPayload }) {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  // ─── Derive state from URL (with defaults + validation) ─────────────
  const rawView = sp.get("view");
  const view: View = (VIEWS as string[]).includes(rawView ?? "")
    ? (rawView as View)
    : DEFAULT_VIEW;

  const rawSort = sp.get("sort");
  const sort: SortKey = (SORT_KEYS as string[]).includes(rawSort ?? "")
    ? (rawSort as SortKey)
    : DEFAULT_SORT;

  const rawOrder = sp.get("order");
  const order: Order =
    rawOrder === "asc" || rawOrder === "desc"
      ? rawOrder
      : DEFAULT_ORDER_FOR_SORT[sort];

  const q = sp.get("search") ?? DEFAULT_SEARCH;

  // ─── URL-update helper: omit defaults, use router.replace, no scroll ─
  const updateParams = (changes: Partial<{ view: View; sort: SortKey; order: Order; search: string }>) => {
    const next = {
      view: changes.view ?? view,
      sort: changes.sort ?? sort,
      // When sort changes and order isn't explicitly being set, reset to that sort's default.
      order:
        changes.order ??
        (changes.sort && changes.sort !== sort
          ? DEFAULT_ORDER_FOR_SORT[changes.sort]
          : order),
      search: changes.search ?? q,
    };

    const params = new URLSearchParams();
    if (next.view !== DEFAULT_VIEW) params.set("view", next.view);
    if (next.sort !== DEFAULT_SORT) params.set("sort", next.sort);
    if (next.order !== DEFAULT_ORDER_FOR_SORT[next.sort]) params.set("order", next.order);
    if (next.search !== DEFAULT_SEARCH) params.set("search", next.search);

    const qs = params.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const rows = useMemo(() => {
    const filtered = q.trim()
      ? payload.categories.filter((c) =>
          c.category.toLowerCase().includes(q.toLowerCase())
        )
      : payload.categories;
    return sortRows(filtered, sort, order);
  }, [payload.categories, sort, order, q]);

  const orderIsDefault = order === DEFAULT_ORDER_FOR_SORT[sort];

  return (
    <div>
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 mb-6">
        <input
          type="search"
          placeholder="Filter categories…"
          value={q}
          onChange={(e) => updateParams({ search: e.target.value })}
          className="w-full sm:w-64 h-9 px-3 rounded-md bg-foreground/5 border border-foreground/15 text-sm placeholder:text-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        <div className="flex items-center gap-2 sm:ml-auto">
          <ArrowUpDown className="size-4 text-foreground/50" />
          <select
            value={sort}
            onChange={(e) => updateParams({ sort: e.target.value as SortKey })}
            className="h-9 px-3 rounded-md bg-foreground/5 border border-foreground/15 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={() =>
              updateParams({ order: order === "asc" ? "desc" : "asc" })
            }
            aria-label={`Sort ${order === "asc" ? "ascending" : "descending"}; click to flip`}
            className={cn(
              "h-9 w-9 inline-flex items-center justify-center rounded-md border border-foreground/15 text-foreground/70 hover:bg-foreground/5 hover:text-foreground transition-colors",
              !orderIsDefault && "text-accent border-accent/40"
            )}
            title={`order=${order}${orderIsDefault ? " (default)" : ""}`}
          >
            {order === "asc" ? (
              <ArrowUp className="size-4" />
            ) : (
              <ArrowDown className="size-4" />
            )}
          </button>
          <div className="inline-flex rounded-md border border-foreground/15 overflow-hidden">
            <button
              type="button"
              onClick={() => updateParams({ view: "grid" })}
              className={cn(
                "h-9 px-3 inline-flex items-center gap-1.5 text-sm",
                view === "grid"
                  ? "bg-foreground/10 text-foreground"
                  : "text-foreground/60 hover:bg-foreground/5"
              )}
              aria-pressed={view === "grid"}
            >
              <LayoutGrid className="size-4" /> Grid
            </button>
            <button
              type="button"
              onClick={() => updateParams({ view: "table" })}
              className={cn(
                "h-9 px-3 inline-flex items-center gap-1.5 text-sm border-l border-foreground/15",
                view === "table"
                  ? "bg-foreground/10 text-foreground"
                  : "text-foreground/60 hover:bg-foreground/5"
              )}
              aria-pressed={view === "table"}
            >
              <TableIcon className="size-4" /> Table
            </button>
          </div>
        </div>
      </div>

      {/* Result count */}
      <p className="text-xs text-foreground/45 mb-4">
        Showing {rows.length} of {payload.total_categories} categories.
      </p>

      {view === "grid" ? (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {rows.map((r) => (
            <CategoryCard key={r.category} row={r} />
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-foreground/10">
          <table className="w-full text-sm">
            <thead className="bg-foreground/[0.04] text-foreground/70">
              <tr>
                <th className="text-left px-3 py-2 font-medium w-10">#</th>
                <th className="text-left px-3 py-2 font-medium">Category</th>
                <th className="text-right px-3 py-2 font-medium">Services</th>
                <th className="text-right px-3 py-2 font-medium">24h Volume</th>
                <th className="text-right px-3 py-2 font-medium hidden md:table-cell">24h Tx</th>
                <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Avg Price</th>
                <th className="text-right px-3 py-2 font-medium">Real %</th>
                <th className="text-right px-3 py-2 font-medium hidden lg:table-cell">Wash %</th>
                <th className="text-left px-3 py-2 font-medium hidden xl:table-cell w-40">Labels</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr
                  key={r.category}
                  className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
                >
                  <td className="px-3 py-2 font-mono text-foreground/45">{i + 1}</td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/categories/${encodeURIComponent(r.category)}`}
                      className="hover:text-accent"
                    >
                      {prettyCategory(r.category)}
                    </Link>
                    <span className="ml-2 font-mono text-[10px] text-foreground/40">
                      {r.category}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono">{fmtInt(r.services_count)}</td>
                  <td className="px-3 py-2 text-right font-mono">{fmtUsd(r.volume_24h)}</td>
                  <td className="px-3 py-2 text-right font-mono hidden md:table-cell">
                    {fmtInt(r.tx_24h)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono hidden md:table-cell">
                    {r.avg_price != null ? fmtUsd(r.avg_price) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-emerald-400">
                    {r.real_volume_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-rose-400 hidden lg:table-cell">
                    {r.wash_pct.toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 hidden xl:table-cell w-40">
                    <LabelMiniBar distribution={r.label_distribution} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
