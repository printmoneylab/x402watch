/**
 * Service data fetched from Oracle FastAPI:
 *   GET /api/v1/services?... (filtered, paginated, sorted)
 *   GET /api/v1/services/{id}  (detail)
 *
 * URL params on the /services page mirror the API query params for
 * shareability / back-button preservation (see ServicesView).
 */
export const SERVICES_REVALIDATE = 300;

const API_BASE =
  process.env.NEXT_PUBLIC_X402WATCH_API ?? "https://api.x402.printmoneylab.com/api/v1";

export type ServiceRow = {
  id: number;
  chain: string;
  seller_address: string;
  resource_url: string | null;
  name: string;
  description: string;
  category: string;
  price_amount: number | null;
  first_seen: string | null;
  tx_24h: number;
  volume_24h: number;
  tx_total: number;
  real_volume_pct: number;
  wash_pct: number;
  label_distribution: Record<string, number>;
};

export type ServiceListPayload = {
  services: ServiceRow[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
  summary: {
    total_volume_24h: number;
    total_tx_24h: number;
  };
  filters_applied: Record<string, unknown>;
};

export type ServiceDetail = {
  service: {
    id: number;
    chain: string;
    seller_address: string;
    resource_url: string | null;
    name: string | null;
    description: string | null;
    category: string;
    price_amount: number | null;
    first_seen: string | null;
    last_seen: string | null;
    real_volume_pct: number;
    wash_pct: number;
    developer_volume_pct: number;
  };
  stats: {
    tx_total: number;
    volume_total: number;
    tx_24h: number;
    volume_24h: number;
  };
  time_series_30d: { date: string; tx_count: number; volume: number }[];
  label_distribution: { label: string; n_tx: number; share_pct: number }[];
  top_buyers: {
    buyer_address: string;
    label: string | null;
    confidence: number | null;
    tx_count: number;
    volume: number;
  }[];
};

export type ServiceFilters = {
  search?: string;
  category?: string;
  chain?: string;
  price_bucket?: string;
  min_real_pct?: number;
  max_wash_pct?: number;
  active_only?: boolean;
  show_placeholder?: boolean;
  sort?: SortKey;
  order?: "asc" | "desc";
  page?: number;
};

export const SORT_KEYS = [
  "tx_24h",
  "volume_24h",
  "tx_total",
  "price",
  "real_pct",
  "wash_pct",
  "first_seen",
  "alpha",
] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export const SORT_LABELS: Record<SortKey, string> = {
  tx_24h:     "24h Tx",
  volume_24h: "24h Volume",
  tx_total:   "Total Tx",
  price:      "Price",
  real_pct:   "Real %",
  wash_pct:   "Wash % (suspect first)",
  first_seen: "First seen (newest)",
  alpha:      "Name (A-Z)",
};

export const DEFAULT_ORDER_FOR_SORT: Record<SortKey, "asc" | "desc"> = {
  tx_24h: "desc",
  volume_24h: "desc",
  tx_total: "desc",
  price: "asc",
  real_pct: "desc",
  wash_pct: "desc",
  first_seen: "desc",
  alpha: "asc",
};

export const PRICE_BUCKETS: { value: string; label: string }[] = [
  { value: "lt_001",  label: "< $0.001" },
  { value: "001_005", label: "$0.001 - $0.005" },
  { value: "005_01",  label: "$0.005 - $0.01" },
  { value: "01_05",   label: "$0.01 - $0.05" },
  { value: "05_1",    label: "$0.05 - $0.1" },
  { value: "gt_1",    label: "$0.1+" },
];

export const CHAINS = ["base", "solana", "arbitrum", "base-sepolia"] as const;

export function buildServicesQuery(f: ServiceFilters): string {
  const p = new URLSearchParams();
  if (f.search) p.set("search", f.search);
  if (f.category) p.set("category", f.category);
  if (f.chain) p.set("chain", f.chain);
  if (f.price_bucket) p.set("price_bucket", f.price_bucket);
  if (f.min_real_pct != null) p.set("min_real_pct", String(f.min_real_pct));
  if (f.max_wash_pct != null) p.set("max_wash_pct", String(f.max_wash_pct));
  if (f.active_only) p.set("active_only", "true");
  if (f.show_placeholder) p.set("show_placeholder", "true");
  if (f.sort && f.sort !== "tx_24h") p.set("sort", f.sort);
  if (f.order && f.order !== DEFAULT_ORDER_FOR_SORT[f.sort ?? "tx_24h"])
    p.set("order", f.order);
  if (f.page && f.page > 1) p.set("page", String(f.page));
  return p.toString();
}

export async function fetchServices(filters: ServiceFilters): Promise<ServiceListPayload> {
  const qs = buildServicesQuery(filters);
  const url = qs ? `${API_BASE}/services?${qs}` : `${API_BASE}/services`;
  const res = await fetch(url, { next: { revalidate: SERVICES_REVALIDATE } });
  if (!res.ok) throw new Error(`services list failed: ${res.status}`);
  return res.json();
}

export async function fetchServiceDetail(id: number | string): Promise<ServiceDetail | null> {
  const res = await fetch(`${API_BASE}/services/${id}`, {
    next: { revalidate: SERVICES_REVALIDATE },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`service detail failed: ${res.status}`);
  return res.json();
}
