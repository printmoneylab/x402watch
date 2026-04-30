/**
 * Wash report data fetched from Oracle FastAPI:
 *   GET /api/v1/wash-report
 *
 * Case studies are anonymized server-side: only `anonymous_id` ("A", "B"…)
 * and pattern signals are returned — never service names or seller
 * addresses. The frontend trusts the API to enforce that.
 */
export const WASH_REVALIDATE = 300;

const API_BASE =
  process.env.NEXT_PUBLIC_X402WATCH_API ?? "https://api.x402.printmoneylab.com/api/v1";

export const WASH_LABELS = [
  "organic_user",
  "self_test",
  "developer",
  "suspected_wash",
  "ai_agent",
  "analytics_bot",
  "exchange_user",
  "verifier",
] as const;

export type WashLabel = (typeof WASH_LABELS)[number];

/** One-line definition + example pattern shown next to the donut. */
export const WASH_LABEL_INFO: Record<WashLabel, { definition: string; pattern: string }> = {
  organic_user: {
    definition: "A real user with diverse, unpredictable browsing patterns.",
    pattern: "Variable inter-tx gaps · mixed services · irregular hours.",
  },
  self_test: {
    definition: "Operator-side wallet calling its own service — not real demand.",
    pattern: "Same wallet hits its own service shortly after deploy; small bursts.",
  },
  developer: {
    definition: "Heavy bot using ≤2 services with near-constant intervals.",
    pattern: "≥80 tx on each of 1–2 services · uniform spacing · long horizon.",
  },
  suspected_wash: {
    definition: "Cohort or vanity cluster gaming volume metrics.",
    pattern: "Many wallets · uniform price · coordinated start within minutes.",
  },
  ai_agent: {
    definition: "Autonomous agent making varied API calls with adaptive timing.",
    pattern: "Multi-service · variable prompt patterns · retries on failure.",
  },
  analytics_bot: {
    definition: "Read-only monitor or data-collection script.",
    pattern: "Predictable cron · GET-shaped traffic · narrow surface.",
  },
  exchange_user: {
    definition: "Wallets sourced from CEX hot-wallet patterns.",
    pattern: "Multi-hop deposit traces · short bursts · withdrawal cadence.",
  },
  verifier: {
    definition: "Validator/oracle node spot-checking outputs.",
    pattern: "Repeated identical queries · signature verification cadence.",
  },
};

export type WashStats = {
  total_active_buyers_30d: number;
  real_volume_pct: number;
  suspected_wash_count: number;
  self_test_count: number;
  last_updated: string;
};

export type WashTimeSeriesPoint = {
  date: string;
  wash_pct: number;
  self_test_pct: number;
};

export type WashCaseStudy = {
  /** Backend assigns these — "A", "B", "C", … — never a real name. */
  anonymous_id: string;
  pattern_type: string;
  buyer_count: number;
  confidence: number;
  wash_pct: number;
  signals: string[];
  details: string[];
};

export type WashReportPayload = {
  stats: WashStats;
  label_distribution: Partial<Record<WashLabel, number>>;
  wash_pct_time_series: WashTimeSeriesPoint[];
  case_studies: WashCaseStudy[];
};

export const WASH_FALLBACK: WashReportPayload = {
  stats: {
    total_active_buyers_30d: 0,
    real_volume_pct: 0,
    suspected_wash_count: 0,
    self_test_count: 0,
    last_updated: "",
  },
  label_distribution: {},
  wash_pct_time_series: [],
  case_studies: [],
};

export async function fetchWashReport(): Promise<WashReportPayload> {
  const res = await fetch(`${API_BASE}/wash-report`, {
    next: { revalidate: WASH_REVALIDATE },
  });
  if (!res.ok) throw new Error(`wash report failed: ${res.status}`);
  return res.json();
}

/** "sophisticated_sybil" → "Sophisticated Sybil Farm" for human-friendly badges. */
export function prettyPatternType(t: string): string {
  const map: Record<string, string> = {
    sophisticated_sybil: "Sophisticated Sybil Farm",
    vanity_cluster: "Vanity Cluster",
    operator_self_test: "Operator Self-Test",
    heavy_bot_developer: "Heavy Bot / Developer",
    clean_organic: "Clean Organic Service",
  };
  if (map[t]) return map[t];
  return t
    .split("_")
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1))
    .join(" ");
}

/** Tone for the pattern-type badge: pattern itself signals colour. */
export function patternTone(t: string): "rose" | "amber" | "orange" | "emerald" | "slate" {
  if (t === "sophisticated_sybil" || t === "vanity_cluster") return "rose";
  if (t === "operator_self_test") return "amber";
  if (t === "heavy_bot_developer") return "orange";
  if (t === "clean_organic") return "emerald";
  return "slate";
}
