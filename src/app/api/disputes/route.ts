/**
 * POST /api/disputes — public label-dispute submission.
 *
 * Flow (Cloudflare Pages Edge runtime):
 *   1. Validate input (wallet format, reason length, label in taxonomy).
 *   2. Rate-limit per IP via Workers KV:
 *        - 10 disputes / hour / IP
 *        - 1 same buyer / 24h / IP
 *        - 1 same (buyer, seller) pair / 24h / IP
 *        - 50+ in an hour → ban for 24h
 *   3. Proxy to Oracle FastAPI `POST /api/v1/internal/disputes` with a
 *      shared secret. Oracle owns the DB, deduplication, telegram alert,
 *      and the recompute_queue trigger when N pending disputes pile up.
 *
 * The frontend never talks to the DB directly — CF Pages Edge has no
 * asyncpg path to Oracle ARM, so the route stays an Edge proxy.
 */
import { NextResponse } from "next/server";
import { getRequestContext } from "@cloudflare/next-on-pages";
import {
  bumpRateLimit,
  banIp,
  isBanned,
  clientIp,
  oracleBase,
  validateDispute,
} from "@/lib/disputes";

export const runtime = "edge";

const IP_PER_HOUR = 10;
const SAME_BUYER_PER_DAY = 1;
const SAME_PAIR_PER_DAY = 1;
const BAN_THRESHOLD = 50;
const HOUR = 3600;
const DAY = 86400;

export async function POST(req: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const v = validateDispute(body as Record<string, unknown>);
  if (!v.ok) {
    return NextResponse.json({ ok: false, error: v.error }, { status: 400 });
  }

  let env: CloudflareEnv;
  try {
    env = getRequestContext().env;
  } catch {
    // Local dev outside `wrangler pages dev` — accept but don't persist.
    return NextResponse.json({
      ok: true,
      persisted: false,
      message: "local dev: dispute not persisted",
    });
  }

  if (!env.WAITLIST_KV) {
    return NextResponse.json(
      { ok: false, error: "kv_unavailable" },
      { status: 503 }
    );
  }

  const ip = clientIp(req);

  if (await isBanned(env.WAITLIST_KV, ip)) {
    return NextResponse.json(
      { ok: false, error: "ip_banned" },
      { status: 429 }
    );
  }

  // Hour-window IP counter (governs both rate and ban escalation).
  const ipBump = await bumpRateLimit(env.WAITLIST_KV, "ip", ip, BAN_THRESHOLD, HOUR);
  if (ipBump.count > BAN_THRESHOLD) {
    await banIp(env.WAITLIST_KV, ip);
    return NextResponse.json(
      { ok: false, error: "ip_banned" },
      { status: 429 }
    );
  }
  if (ipBump.count > IP_PER_HOUR) {
    return NextResponse.json(
      { ok: false, error: "rate_limit_exceeded" },
      { status: 429 }
    );
  }

  // 24h same-buyer guard
  const buyerKey = `${ip}:${v.clean.buyer_address.toLowerCase()}`;
  const buyerBump = await bumpRateLimit(
    env.WAITLIST_KV,
    "buyer",
    buyerKey,
    SAME_BUYER_PER_DAY,
    DAY
  );
  if (buyerBump.limited) {
    return NextResponse.json(
      { ok: false, error: "duplicate" },
      { status: 429 }
    );
  }

  // 24h same-pair guard (only if a seller was supplied)
  if (v.clean.seller_address) {
    const pairKey = `${ip}:${v.clean.buyer_address.toLowerCase()}:${v.clean.seller_address.toLowerCase()}`;
    const pairBump = await bumpRateLimit(
      env.WAITLIST_KV,
      "pair",
      pairKey,
      SAME_PAIR_PER_DAY,
      DAY
    );
    if (pairBump.limited) {
      return NextResponse.json(
        { ok: false, error: "duplicate" },
        { status: 429 }
      );
    }
  }

  // Forward to Oracle FastAPI internal endpoint.
  const token = env.X402_INTERNAL_TOKEN;
  if (!token) {
    console.error("[disputes] X402_INTERNAL_TOKEN not configured");
    return NextResponse.json(
      { ok: false, error: "internal_unavailable" },
      { status: 503 }
    );
  }

  const url = `${oracleBase(env)}/internal/disputes`;
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        "X-Forwarded-IP": ip,
      },
      body: JSON.stringify(v.clean),
      signal: AbortSignal.timeout(8000),
    });
  } catch (err) {
    console.error("[disputes] upstream fetch failed:", err);
    return NextResponse.json(
      { ok: false, error: "upstream_unavailable" },
      { status: 502 }
    );
  }

  let upstreamBody: unknown = null;
  try {
    upstreamBody = await upstream.json();
  } catch {
    /* ignore — non-JSON body */
  }

  if (!upstream.ok) {
    const errStr =
      (upstreamBody && typeof upstreamBody === "object" && "error" in upstreamBody &&
        typeof (upstreamBody as { error: unknown }).error === "string")
        ? (upstreamBody as { error: string }).error
        : `upstream_${upstream.status}`;
    return NextResponse.json(
      { ok: false, error: errStr },
      { status: upstream.status >= 500 ? 502 : upstream.status }
    );
  }

  return NextResponse.json({ ok: true, ...(typeof upstreamBody === "object" ? upstreamBody : {}) });
}
