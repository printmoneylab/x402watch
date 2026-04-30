/**
 * Stats fetched at request time and cached for 60 seconds (matches the
 * Oracle Redis cache TTL).
 *
 * Data flow: Next.js Server Component → fetch(API_URL, {revalidate: 60}) →
 *   Oracle FastAPI /api/v1/landing-stats → Redis cache (60s TTL) → PostgreSQL.
 */
export const REVALIDATE_SECONDS = 60;

const API_BASE =
  process.env.NEXT_PUBLIC_X402WATCH_API ?? "https://x402.printmoneylab.com/api/v1";

export type LandingStats = {
  services_indexed: number;
  transactions_analyzed: number;
  active_buyers: number;
  real_volume_pct: number;
  last_updated: string;
};

export type LabelDistribution = {
  label: string;
  n_buyers: number;
  share_pct: number;
}[];

export type CategoryVolumeSeries = {
  category: string;
  points: { date: string; total_volume_24h: number; total_tx_24h: number }[];
}[];

export type DailyNewServices = { date: string; count: number }[];

export type LandingPayload = {
  stats: LandingStats;
  label_distribution: LabelDistribution;
  category_volume_series: CategoryVolumeSeries;
  daily_new_services: DailyNewServices;
};

export async function fetchLandingPayload(): Promise<LandingPayload> {
  const res = await fetch(`${API_BASE}/landing-stats`, {
    next: { revalidate: REVALIDATE_SECONDS },
  });
  if (!res.ok) {
    throw new Error(`landing-stats failed: ${res.status}`);
  }
  return res.json();
}

/** Static fallback so the page renders when the API is unreachable in dev. */
export const FALLBACK: LandingPayload = {
  stats: {
    services_indexed: 35395,
    transactions_analyzed: 307571,
    active_buyers: 1970,
    real_volume_pct: 83.4,
    last_updated: new Date().toISOString(),
  },
  label_distribution: [
    { label: "organic_user", n_buyers: 1372, share_pct: 69.6 },
    { label: "self_test", n_buyers: 240, share_pct: 12.2 },
    { label: "developer", n_buyers: 192, share_pct: 9.7 },
    { label: "suspected_wash", n_buyers: 150, share_pct: 7.6 },
    { label: "ai_agent", n_buyers: 12, share_pct: 0.6 },
    { label: "analytics_bot", n_buyers: 4, share_pct: 0.2 },
  ],
  category_volume_series: [],
  daily_new_services: [],
};
