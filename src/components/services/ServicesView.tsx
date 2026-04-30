"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams, usePathname } from "next/navigation";
import {
  LayoutGrid,
  Table as TableIcon,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  X,
  Loader2,
} from "lucide-react";
import { ServiceCard } from "./ServiceCard";
import { ServiceTable } from "./ServiceTable";
import { Pagination } from "./Pagination";
import {
  CHAINS,
  PRICE_BUCKETS,
  SORT_KEYS,
  SORT_LABELS,
  DEFAULT_ORDER_FOR_SORT,
  PER_PAGE_OPTIONS,
  DEFAULT_PER_PAGE,
  isPerPage,
  type PerPage,
  type ServiceListPayload,
  type SortKey,
} from "@/lib/services";
import { cn } from "@/lib/utils";

const PER_PAGE_STORAGE_KEY = "x402watch:services:per_page";

type View = "grid" | "table";
const VIEWS: View[] = ["grid", "table"];

const DEFAULT_VIEW: View = "grid";
const DEFAULT_SORT: SortKey = "tx_24h";

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K` : `$${n.toFixed(2)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

export function ServicesView({
  initialPayload,
  categories,
}: {
  initialPayload: ServiceListPayload;
  categories: string[];
}) {
  const sp = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  // Derive state from URL
  const view: View = (VIEWS as string[]).includes(sp.get("view") ?? "")
    ? (sp.get("view") as View)
    : DEFAULT_VIEW;
  const sort: SortKey = (SORT_KEYS as readonly string[]).includes(sp.get("sort") ?? "")
    ? (sp.get("sort") as SortKey)
    : DEFAULT_SORT;
  const rawOrder = sp.get("order");
  const order: "asc" | "desc" =
    rawOrder === "asc" || rawOrder === "desc" ? rawOrder : DEFAULT_ORDER_FOR_SORT[sort];
  const search = sp.get("search") ?? "";
  const category = sp.get("category") ?? "";
  const chain = sp.get("chain") ?? "";
  const priceBucket = sp.get("price_bucket") ?? "";
  const minRealPct = sp.get("min_real_pct") ?? "";
  const maxWashPct = sp.get("max_wash_pct") ?? "";
  const activeOnly = sp.get("active_only") === "true";
  const showPlaceholder = sp.get("show_placeholder") === "true";
  const perPageRaw = parseInt(sp.get("per_page") ?? "", 10);
  const perPage: PerPage = isPerPage(perPageRaw) ? perPageRaw : DEFAULT_PER_PAGE;

  // Local search input state to avoid URL update on every keystroke;
  // commits on Enter / blur via updateParams. Re-sync on URL changes
  // (back/forward navigation, reset, etc.) by adjusting state during
  // render when the URL `search` value diverges from what we last saw —
  // this is React's recommended "derived from prop" pattern and
  // guarantees the input never drifts out of sync with `?search=`.
  const [searchDraft, setSearchDraft] = useState(search);
  const [lastSeenSearch, setLastSeenSearch] = useState(search);
  if (search !== lastSeenSearch) {
    setLastSeenSearch(search);
    setSearchDraft(search);
  }

  // Loading shimmer: any URL change means the in-flight navigation
  // settled. Reset during render when `sp` changes since last seen.
  const [pending, setPending] = useState(false);
  const [lastSeenSp, setLastSeenSp] = useState(sp);
  if (sp !== lastSeenSp) {
    setLastSeenSp(sp);
    if (pending) setPending(false);
  }

  const update = (
    changes: Record<string, string | boolean | number | null | undefined>,
    opts: { resetPage?: boolean } = {}
  ) => {
    const next = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v == null || v === "" || v === false) next.delete(k);
      else next.set(k, String(v));
    }
    if (opts.resetPage) next.delete("page");
    // Strip default values
    if (next.get("view") === DEFAULT_VIEW) next.delete("view");
    if (next.get("sort") === DEFAULT_SORT) next.delete("sort");
    const sortNow = (next.get("sort") as SortKey) ?? DEFAULT_SORT;
    if (next.get("order") === DEFAULT_ORDER_FOR_SORT[sortNow]) next.delete("order");
    if (next.get("page") === "1") next.delete("page");
    if (next.get("per_page") === String(DEFAULT_PER_PAGE)) next.delete("per_page");

    const qs = next.toString();
    setPending(true);
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  // On mount, if the URL doesn't pin a per_page, apply the user's
  // remembered preference from localStorage. Runs once; uses a ref guard
  // so it survives re-renders without re-firing. Calls router.replace
  // directly (rather than `update`) because `update` flips local state,
  // which would be a setState-in-effect.
  const didApplyStoredPerPageRef = useRef(false);
  useEffect(() => {
    if (didApplyStoredPerPageRef.current) return;
    didApplyStoredPerPageRef.current = true;
    if (sp.get("per_page")) return;
    if (typeof window === "undefined") return;
    const stored = window.localStorage.getItem(PER_PAGE_STORAGE_KEY);
    if (!stored) return;
    const parsed = parseInt(stored, 10);
    if (!isPerPage(parsed) || parsed === DEFAULT_PER_PAGE) return;
    const next = new URLSearchParams(sp.toString());
    next.set("per_page", String(parsed));
    next.delete("page");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePerPageChange = (next: PerPage) => {
    if (typeof window !== "undefined") {
      if (next === DEFAULT_PER_PAGE) {
        window.localStorage.removeItem(PER_PAGE_STORAGE_KEY);
      } else {
        window.localStorage.setItem(PER_PAGE_STORAGE_KEY, String(next));
      }
    }
    update(
      { per_page: next === DEFAULT_PER_PAGE ? null : next },
      { resetPage: true }
    );
  };

  const reset = () => {
    setPending(true);
    router.replace(pathname, { scroll: false });
  };

  const orderIsDefault = order === DEFAULT_ORDER_FOR_SORT[sort];
  const hasActiveFilter =
    !!search || !!category || !!chain || !!priceBucket ||
    !!minRealPct || !!maxWashPct || activeOnly || showPlaceholder ||
    sort !== DEFAULT_SORT || !orderIsDefault || view !== DEFAULT_VIEW;

  const { services, pagination, summary } = initialPayload;
  const pageStart = (pagination.page - 1) * pagination.page_size + 1;

  // Same-seller grouping: when several visible cards share a seller, give
  // each shared seller a colored dot so the operator behind the listings is
  // visually obvious. Singletons get no dot (avoids visual noise).
  const sellerDotMap = useMemo(() => {
    const SELLER_DOT_PALETTE = [
      "bg-rose-400",
      "bg-emerald-400",
      "bg-sky-400",
      "bg-amber-400",
      "bg-violet-400",
      "bg-cyan-400",
      "bg-pink-400",
      "bg-teal-400",
    ];
    const counts = new Map<string, number>();
    for (const s of services) {
      if (!s.seller_address) continue;
      counts.set(s.seller_address, (counts.get(s.seller_address) ?? 0) + 1);
    }
    const map = new Map<string, string>();
    let i = 0;
    for (const s of services) {
      const addr = s.seller_address;
      if (!addr) continue;
      if ((counts.get(addr) ?? 0) > 1 && !map.has(addr)) {
        map.set(addr, SELLER_DOT_PALETTE[i % SELLER_DOT_PALETTE.length]);
        i++;
      }
    }
    return map;
  }, [services]);

  return (
    <div>
      {/* Stats bar */}
      <div className="flex flex-col sm:flex-row sm:items-baseline gap-2 sm:gap-6 mb-6 text-sm">
        <div className="font-mono text-foreground/85">
          {fmtInt(pagination.total)} services
        </div>
        <div className="text-foreground/55">
          page {pagination.page} of {Math.max(1, pagination.total_pages)}
        </div>
        <div className="text-foreground/55">
          24h: {fmtInt(summary.total_tx_24h)} tx · {fmtUsd(summary.total_volume_24h)}
        </div>
        {pending && (
          <span className="ml-auto inline-flex items-center gap-1 text-foreground/50 text-xs">
            <Loader2 className="size-3.5 animate-spin" /> updating
          </span>
        )}
      </div>

      {/* Filter bar */}
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-4 mb-6">
        <div className="flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="search"
              placeholder="Search name, description, or seller…"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  update({ search: searchDraft || null }, { resetPage: true });
                }
              }}
              onBlur={() => {
                if (searchDraft !== search)
                  update({ search: searchDraft || null }, { resetPage: true });
              }}
              className="flex-1 h-9 px-3 rounded-md bg-foreground/5 border border-foreground/15 text-sm placeholder:text-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
            {hasActiveFilter && (
              <button
                type="button"
                onClick={reset}
                className="inline-flex items-center gap-1 h-9 px-3 rounded-md text-sm border border-foreground/15 text-foreground/70 hover:bg-foreground/5 hover:text-foreground"
              >
                <X className="size-4" /> Reset
              </button>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            <select
              value={category}
              onChange={(e) =>
                update({ category: e.target.value || null }, { resetPage: true })
              }
              className="h-9 px-2 rounded-md bg-foreground/5 border border-foreground/15 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <select
              value={chain}
              onChange={(e) => update({ chain: e.target.value || null }, { resetPage: true })}
              className="h-9 px-2 rounded-md bg-foreground/5 border border-foreground/15 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              <option value="">All chains</option>
              {CHAINS.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <select
              value={priceBucket}
              onChange={(e) =>
                update({ price_bucket: e.target.value || null }, { resetPage: true })
              }
              className="h-9 px-2 rounded-md bg-foreground/5 border border-foreground/15 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              <option value="">All prices</option>
              {PRICE_BUCKETS.map((b) => (
                <option key={b.value} value={b.value}>{b.label}</option>
              ))}
            </select>
            <input
              type="number"
              min="0"
              max="100"
              placeholder="Min Real %"
              value={minRealPct}
              onChange={(e) =>
                update({ min_real_pct: e.target.value || null }, { resetPage: true })
              }
              className="h-9 px-2 rounded-md bg-foreground/5 border border-foreground/15 text-sm placeholder:text-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
            <input
              type="number"
              min="0"
              max="100"
              placeholder="Max Wash %"
              value={maxWashPct}
              onChange={(e) =>
                update({ max_wash_pct: e.target.value || null }, { resetPage: true })
              }
              className="h-9 px-2 rounded-md bg-foreground/5 border border-foreground/15 text-sm placeholder:text-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
            <div className="flex items-center gap-3 text-xs text-foreground/70 col-span-2 sm:col-span-1 lg:col-span-1">
              <label className="inline-flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={activeOnly}
                  onChange={(e) =>
                    update({ active_only: e.target.checked }, { resetPage: true })
                  }
                  className="accent-accent"
                />
                Active only
              </label>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs text-foreground/70">
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={showPlaceholder}
                onChange={(e) =>
                  update({ show_placeholder: e.target.checked }, { resetPage: true })
                }
                className="accent-accent"
              />
              Show <span className="font-mono">premium_placeholder</span>
            </label>
          </div>
        </div>
      </div>

      {/* Sort + view toggle row */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <ArrowUpDown className="size-4 text-foreground/50" />
        <select
          value={sort}
          onChange={(e) => update({ sort: e.target.value as SortKey }, { resetPage: true })}
          className="h-9 px-3 rounded-md bg-foreground/5 border border-foreground/15 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          {SORT_KEYS.map((k) => (
            <option key={k} value={k}>{SORT_LABELS[k]}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={() =>
            update({ order: order === "asc" ? "desc" : "asc" }, { resetPage: true })
          }
          className={cn(
            "h-9 w-9 inline-flex items-center justify-center rounded-md border border-foreground/15 text-foreground/70 hover:bg-foreground/5 hover:text-foreground transition-colors",
            !orderIsDefault && "text-accent border-accent/40"
          )}
          aria-label={`Sort ${order}; click to flip`}
        >
          {order === "asc" ? <ArrowUp className="size-4" /> : <ArrowDown className="size-4" />}
        </button>

        <label className="ml-auto sm:ml-2 inline-flex items-center gap-1.5 text-xs text-foreground/55">
          <span className="hidden sm:inline">Per page</span>
          <select
            value={perPage}
            onChange={(e) => handlePerPageChange(Number(e.target.value) as PerPage)}
            className="h-9 px-2 rounded-md bg-foreground/5 border border-foreground/15 text-sm font-mono text-foreground/85 focus:outline-none focus:ring-2 focus:ring-accent/40"
            aria-label="Items per page"
          >
            {PER_PAGE_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>

        <div className="inline-flex rounded-md border border-foreground/15 overflow-hidden">
          <button
            type="button"
            onClick={() => update({ view: "grid" })}
            className={cn(
              "h-9 px-3 inline-flex items-center gap-1.5 text-sm",
              view === "grid"
                ? "bg-foreground/10 text-foreground"
                : "text-foreground/60 hover:bg-foreground/5"
            )}
          >
            <LayoutGrid className="size-4" /> Grid
          </button>
          <button
            type="button"
            onClick={() => update({ view: "table" })}
            className={cn(
              "h-9 px-3 inline-flex items-center gap-1.5 text-sm border-l border-foreground/15",
              view === "table"
                ? "bg-foreground/10 text-foreground"
                : "text-foreground/60 hover:bg-foreground/5"
            )}
          >
            <TableIcon className="size-4" /> Table
          </button>
        </div>
      </div>

      {/* Results */}
      {services.length === 0 ? (
        <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-12 text-center text-sm text-foreground/55">
          No services match the current filters.{" "}
          <button onClick={reset} className="text-accent hover:underline">
            Reset filters
          </button>
        </div>
      ) : view === "grid" ? (
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((s) => (
            <ServiceCard
              key={s.id}
              row={s}
              sellerDotClass={sellerDotMap.get(s.seller_address)}
            />
          ))}
        </div>
      ) : (
        <ServiceTable rows={services} pageStart={pageStart} />
      )}

      <Pagination
        page={pagination.page}
        totalPages={pagination.total_pages}
        onChange={(p) => update({ page: p > 1 ? p : null })}
      />
    </div>
  );
}
