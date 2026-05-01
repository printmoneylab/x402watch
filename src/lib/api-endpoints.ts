/**
 * Pricing + descriptions for the public x402 API. Single source of truth
 * — change here and the /api page updates. The strings here drive both
 * the UI and (eventually) the live spec.
 */
import type { PaidEndpoint } from "@/components/api/PaidEndpointCard";

export type FreeEndpoint = {
  path: string;
  description: string;
  rateLimit: string;
};

export const FREE_ENDPOINTS: FreeEndpoint[] = [
  {
    path: "GET /api/v1/landing-stats",
    description: "Real-time market overview (services, transactions, real volume %).",
    rateLimit: "60/hour",
  },
  {
    path: "GET /api/v1/categories",
    description: "All 33 x402 service categories with stats.",
    rateLimit: "60/hour",
  },
  {
    path: "GET /api/v1/categories/{slug}",
    description: "Category detail + 30-day time series + top services.",
    rateLimit: "60/hour",
  },
  {
    path: "GET /api/v1/services",
    description: "Paginated list of indexed x402 services with filters.",
    rateLimit: "60/hour",
  },
  {
    path: "GET /api/v1/services/{id}",
    description: "Service detail: stats, time series, top buyers, label distribution.",
    rateLimit: "60/hour",
  },
  {
    path: "GET /api/v1/trends",
    description: "24-hour ecosystem trends: new services, volume movers, hot services.",
    rateLimit: "60/hour",
  },
  {
    path: "GET /api/v1/wash-report",
    description: "Aggregate wash patterns + anonymized case studies.",
    rateLimit: "60/hour",
  },
];

export const PAID_ENDPOINTS: PaidEndpoint[] = [
  {
    method: "GET",
    path: "/api/v1/services/{id}/wash-detail",
    priceUsd: 0.005,
    useCase: "Operator audit",
    description:
      "Top 50 buyers per service with full label classification, confidence scores, and signal-by-signal breakdown. Includes vanity cluster detection, cohort signals (uniform_amount, coordinated_start, etc.), and per-buyer transaction history. Operators use this to audit their own service's traffic composition.",
    request: `curl -X GET https://api.x402.printmoneylab.com/api/v1/services/14388/wash-detail \\
  -H "X-PAYMENT: <base64 payment>"`,
    responseShape: `{
  service_id: number;
  buyers: Array<{
    address: string;
    label: WashLabel;
    confidence: number;
    signals: Record<string, number>;
    tx_count: number;
    volume: number;
  }>;
  cohort_summary: {
    uniform_amount_pct: number;
    coordinated_start_pct: number;
    uniform_tx_count_cv: number;
    cohort_size: number;
  };
}`,
    sample: `{
  "service_id": 14388,
  "buyers": [
    { "address": "0x29b...725", "label": "suspected_wash",
      "confidence": 0.93,
      "signals": { "uniform_amount": 0.97, "coordinated_start": 0.88 },
      "tx_count": 79, "volume": 1.58 }
  ],
  "cohort_summary": { "cohort_size": 60, "uniform_amount_pct": 97 }
}`,
  },
  {
    method: "GET",
    path: "/api/v1/buyers/{address}/profile",
    priceUsd: 0.005,
    useCase: "Wallet research",
    description:
      "Single buyer wallet's 8-label classification with confidence, all services they've used, transaction patterns, time clustering, vanity cluster membership. Researchers use this to trace specific wallets across the x402 ecosystem.",
    request: `curl -X GET https://api.x402.printmoneylab.com/api/v1/buyers/0x29b...725/profile \\
  -H "X-PAYMENT: <base64 payment>"`,
    responseShape: `{
  address: string;
  label: WashLabel;
  confidence: number;
  reason: string[];
  services_used: Array<{ id: number; category: string; tx_count: number }>;
  vanity_cluster: { strict: boolean; broad: boolean; size: number } | null;
  time_pattern: { mean_interval_s: number; cv: number };
}`,
    sample: `{
  "address": "0x29b...725",
  "label": "suspected_wash",
  "confidence": 0.90,
  "reason": ["coordinated_start", "uniform_amount", "uniform_tx_count"],
  "services_used": [{ "id": 14388, "category": "authentication", "tx_count": 79 }],
  "vanity_cluster": null
}`,
  },
  {
    method: "GET",
    path: "/api/v1/services/{id}/transactions",
    priceUsd: 0.01,
    useCase: "Custom analysis",
    description:
      "Raw 30-day transaction list for a single service. All USDC payment events including buyer address, amount, timestamp, transaction hash, chain. Up to ~3000 rows per service. Researchers and analysts use this for custom downstream analysis.",
    request: `curl -X GET https://api.x402.printmoneylab.com/api/v1/services/14388/transactions \\
  -H "X-PAYMENT: <base64 payment>"`,
    responseShape: `{
  service_id: number;
  transactions: Array<{
    tx_hash: string;
    chain: "base" | "solana" | "polygon" | "arbitrum";
    buyer: string;
    amount: number;       // USDC
    time: string;         // ISO 8601
  }>;
  total: number;
}`,
    sample: `{
  "service_id": 14388,
  "transactions": [
    { "tx_hash": "0xabc...", "chain": "base",
      "buyer": "0x29b...725", "amount": 0.02,
      "time": "2026-04-30T14:02:17Z" }
  ],
  "total": 2814
}`,
  },
  {
    method: "GET",
    path: "/api/v1/categories/{slug}/full-history",
    priceUsd: 0.02,
    useCase: "Longitudinal research",
    description:
      "365-day hourly time-series for a category: services count, total volume, transaction count, real volume %, label distribution. ~8760 rows per category. Longitudinal research, trend analysis, market reports.",
    request: `curl -X GET https://api.x402.printmoneylab.com/api/v1/categories/ai_inference/full-history \\
  -H "X-PAYMENT: <base64 payment>"`,
    responseShape: `{
  category: string;
  points: Array<{
    time: string;          // ISO hour bucket
    services_count: number;
    volume: number;
    tx_count: number;
    real_volume_pct: number;
  }>;
}`,
    sample: `{
  "category": "ai_inference",
  "points": [
    { "time": "2025-05-01T00:00:00Z",
      "services_count": 1240, "volume": 312.55,
      "tx_count": 1820, "real_volume_pct": 81.2 }
  ]
}`,
  },
  {
    method: "POST",
    path: "/api/v1/wash/check",
    priceUsd: 0.05,
    useCase: "Real-time wash check",
    description:
      "On-demand wash analysis for any wallet or seller address. Returns 8-label classification with confidence, signal breakdown (vanity, cohort, concentration, etc.), and similar pattern matching. Real-time computed (not cached). Use for due diligence, fraud detection, or analyzing new addresses not yet in our index.",
    request: `curl -X POST https://api.x402.printmoneylab.com/api/v1/wash/check \\
  -H "Content-Type: application/json" \\
  -H "X-PAYMENT: <base64 payment>" \\
  -d '{"address": "0x29b...725"}'`,
    responseShape: `{
  address: string;
  label: WashLabel;
  confidence: number;
  signals: {
    vanity: { strict: boolean; broad: boolean };
    cohort: { uniform_amount: number; coordinated_start: number };
    concentration: { top_service_share: number };
  };
  similar_patterns: Array<{ anonymous_id: string; pattern_type: string }>;
}`,
    sample: `{
  "address": "0x29b...725",
  "label": "suspected_wash",
  "confidence": 0.90,
  "signals": {
    "vanity": { "strict": false, "broad": false },
    "cohort": { "uniform_amount": 0.97, "coordinated_start": 0.88 },
    "concentration": { "top_service_share": 0.98 }
  },
  "similar_patterns": [{ "anonymous_id": "A", "pattern_type": "sophisticated_sybil" }]
}`,
  },
];
