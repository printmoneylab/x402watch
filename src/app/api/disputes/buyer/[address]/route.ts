/**
 * GET /api/disputes/buyer/[address] — public count of disputes filed
 * against a given buyer wallet. Used by the future buyer-profile page
 * to render "N reports filed" without exposing the dispute bodies.
 *
 * Edge proxy → Oracle FastAPI `GET /api/v1/disputes/buyer/{address}`.
 * Cached at the Pages edge for 60s to absorb hot-path bursts; Oracle
 * still has the canonical numbers behind it.
 */
import { NextResponse } from "next/server";
import { getRequestContext } from "@cloudflare/next-on-pages";
import { isWalletAddress, oracleBase } from "@/lib/disputes";

export const runtime = "edge";
export const revalidate = 60;

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ address: string }> }
): Promise<Response> {
  const { address } = await ctx.params;
  if (!isWalletAddress(address)) {
    return NextResponse.json({ ok: false, error: "invalid_address" }, { status: 400 });
  }

  let env: CloudflareEnv;
  try {
    env = getRequestContext().env;
  } catch {
    return NextResponse.json({
      ok: true,
      buyer_address: address,
      total_disputes: 0,
      pending: 0,
      reviewed: 0,
      resolved: 0,
      local_dev: true,
    });
  }

  const url = `${oracleBase(env)}/disputes/buyer/${encodeURIComponent(address)}`;
  try {
    const r = await fetch(url, {
      signal: AbortSignal.timeout(5000),
      cf: { cacheTtl: 60, cacheEverything: true },
    } as RequestInit & { cf?: unknown });
    if (!r.ok) {
      return NextResponse.json(
        { ok: false, error: `upstream_${r.status}` },
        { status: 502 }
      );
    }
    const data = (await r.json().catch(() => ({}))) as Record<string, unknown>;
    return NextResponse.json({ ok: true, ...(data || {}) });
  } catch (err) {
    console.error("[disputes/buyer] upstream failed:", err);
    return NextResponse.json(
      { ok: false, error: "upstream_unavailable" },
      { status: 502 }
    );
  }
}
