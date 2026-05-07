import { NextResponse } from "next/server";

export const dynamic = "force-static";

export function GET() {
  const manifest = {
    name: "x402watch",
    description: "Wash-filtered intelligence layer for x402",
    version: "1.0.0",
    api: "https://api.x402.printmoneylab.com/api/v1",
    documentation: "https://x402.printmoneylab.com",
    license: {
      code: "Apache-2.0",
      data: "CC0-1.0",
    },
    endpoints: [
      "/api/v1/landing-stats",
      "/api/v1/categories",
      "/api/v1/categories/{slug}",
      "/api/v1/services",
      "/api/v1/services/{id}",
      "/api/v1/trends",
      "/api/v1/wash-report",
    ],
    paid_endpoints: [
      "GET /api/v1/services/{id}/wash-detail",
      "GET /api/v1/buyers/{address}/profile",
      "GET /api/v1/services/{id}/transactions",
      "GET /api/v1/categories/{slug}/full-history",
      "POST /api/v1/wash/check",
    ],
    networks: [
      { name: "Base", caip2: "eip155:8453", asset: "USDC" },
      { name: "Solana", caip2: "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp", asset: "USDC SPL" },
    ],
  };

  return NextResponse.json(manifest, {
    headers: {
      "Cache-Control": "public, max-age=3600, s-maxage=3600",
    },
  });
}
