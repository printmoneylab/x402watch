/**
 * Category data — fetched from Oracle FastAPI (/api/v1/categories and
 * /api/v1/categories/{slug}). Cached server-side for 5 minutes.
 */
export const CATEGORY_REVALIDATE = 300;

const API_BASE =
  process.env.NEXT_PUBLIC_X402WATCH_API ?? "https://api.x402.printmoneylab.com/api/v1";

export type LabelDistribution = Record<string, number>; // share fractions [0..1]

export type CategoryRow = {
  category: string;
  services_count: number;
  avg_price: number | null;
  median_price: number | null;
  volume_24h: number;
  tx_24h: number;
  real_volume_pct: number;
  wash_pct: number;
  label_distribution: LabelDistribution;
  last_hour?: string;
};

export type CategoryListPayload = {
  categories: CategoryRow[];
  total_categories: number;
  total_services: number;
  total_volume_24h: number;
  total_tx_24h: number;
  last_updated: string;
};

export type CategoryDetailStats = {
  services_count: number;
  avg_price: number | null;
  median_price: number | null;
  volume_24h: number;
  tx_24h: number;
  real_volume_pct: number;
  wash_pct: number;
  last_hour: string | null;
};

export type CategoryTimeSeriesPoint = {
  date: string;
  volume: number;
  tx_count: number;
};

export type CategoryLabelEntry = {
  label: string;
  n_tx: number;
  share_pct: number;
};

export type CategoryPriceBucket = {
  bucket: string;
  count: number;
};

export type TopService = {
  id: number;
  name: string;
  resource_url: string | null;
  price: number | null;
  tx_30d: number;
  volume_30d: number;
  real_pct: number;
  wash_pct: number;
};

export type CategoryDetail = {
  category: string;
  stats: CategoryDetailStats;
  time_series: CategoryTimeSeriesPoint[];
  label_distribution: CategoryLabelEntry[];
  price_distribution: CategoryPriceBucket[];
  top_services: TopService[];
};

export async function fetchCategories(): Promise<CategoryListPayload> {
  const res = await fetch(`${API_BASE}/categories`, {
    next: { revalidate: CATEGORY_REVALIDATE },
  });
  if (!res.ok) throw new Error(`categories list failed: ${res.status}`);
  return res.json();
}

export async function fetchCategoryDetail(slug: string): Promise<CategoryDetail | null> {
  const res = await fetch(`${API_BASE}/categories/${encodeURIComponent(slug)}`, {
    next: { revalidate: CATEGORY_REVALIDATE },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`category detail failed: ${res.status}`);
  return res.json();
}

/** Tailwind colour token per category (kept here so cards + chart segments stay in sync). */
export function categoryAccent(cat: string): "rose" | "emerald" | "sky" | "violet" | "amber" | "slate" {
  if (cat === "token_safety" || cat === "security_scoring") return "rose";
  if (
    cat === "search_engine" ||
    cat === "ai_search" ||
    cat === "ai_inference" ||
    cat === "translation" ||
    cat === "content_generation" ||
    cat === "blockchain_infra"
  ) return "sky";
  if (
    cat === "wallet_analytics" ||
    cat === "defi_data" ||
    cat === "nft_data" ||
    cat === "agent_payments" ||
    cat === "agent_communication"
  ) return "violet";
  if (
    cat === "token_data" ||
    cat === "financial_data" ||
    cat === "trading_signals" ||
    cat === "business_intelligence"
  ) return "emerald";
  if (cat === "premium_placeholder" || cat === "test_dummy" || cat === "other") return "amber";
  return "slate";
}

/** Display-friendly category name. */
export function prettyCategory(cat: string): string {
  return cat
    .split("_")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}

/** Tailwind classes for label colour swatches (mini bars + donut segments). */
export const LABEL_COLOR_TW: Record<string, string> = {
  organic_user: "bg-emerald-500",
  ai_agent: "bg-teal-400",
  exchange_user: "bg-cyan-400",
  developer: "bg-orange-400",
  self_test: "bg-amber-400",
  analytics_bot: "bg-sky-400",
  verifier: "bg-slate-400",
  suspected_wash: "bg-rose-500",
  unlabeled: "bg-zinc-700",
};

export const LABEL_COLOR_HEX: Record<string, string> = {
  organic_user: "#10b981",
  ai_agent: "#2dd4bf",
  exchange_user: "#22d3ee",
  developer: "#fb923c",
  self_test: "#fbbf24",
  analytics_bot: "#7dd3fc",
  verifier: "#94a3b8",
  suspected_wash: "#f43f5e",
  unlabeled: "#3f3f46",
};
