/**
 * Trends data fetched from Oracle FastAPI:
 *   GET /api/v1/trends   (24h-window aggregations)
 *
 * The endpoint is server-rendered into /trends. If the API is unreachable
 * we degrade to an empty payload — sections show "no data" rather than
 * crashing the page.
 */
export const TRENDS_REVALIDATE = 300;

const API_BASE =
  process.env.NEXT_PUBLIC_X402WATCH_API ?? "https://api.x402.printmoneylab.com/api/v1";

export type TrendsSummary = {
  new_services_24h: number;
  new_services_prev_24h: number;
  new_services_change_pct: number;
  total_tx_24h: number;
  total_volume_24h: number;
  active_buyers_24h: number;
};

export type DailyNewServicesPoint = {
  date: string;
  count: number;
};

export type RecentNewService = {
  id: number;
  name: string;
  category: string;
  chain: string;
  price_amount: number | null;
  first_seen: string;
};

export type CategoryMover = {
  category: string;
  volume_24h: number;
  volume_prev: number;
  change_pct: number;
  tx_24h: number;
  tx_prev: number;
  tx_change_pct: number;
};

export type HotService = {
  id: number;
  name: string;
  category: string;
  chain: string;
  tx_24h: number;
  tx_prev: number;
  tx_change_pct: number;
  real_volume_pct: number;
  wash_pct: number;
};

export type TrendsPayload = {
  summary: TrendsSummary;
  daily_new_services: DailyNewServicesPoint[];
  recent_new_services: RecentNewService[];
  category_movers: CategoryMover[];
  hot_services: HotService[];
};

export const TRENDS_FALLBACK: TrendsPayload = {
  summary: {
    new_services_24h: 0,
    new_services_prev_24h: 0,
    new_services_change_pct: 0,
    total_tx_24h: 0,
    total_volume_24h: 0,
    active_buyers_24h: 0,
  },
  daily_new_services: [],
  recent_new_services: [],
  category_movers: [],
  hot_services: [],
};

export async function fetchTrends(): Promise<TrendsPayload> {
  const res = await fetch(`${API_BASE}/trends`, {
    next: { revalidate: TRENDS_REVALIDATE },
  });
  if (!res.ok) throw new Error(`trends failed: ${res.status}`);
  return res.json();
}
