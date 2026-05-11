/**
 * GET /api/disputes/list — admin-only list of recent disputes.
 *
 * Auth: `Authorization: Bearer <ADMIN_TOKEN>` or `?token=...`.
 * Proxies to Oracle FastAPI `GET /api/v1/internal/disputes/list` with
 * the same shared secret that the POST handler uses. Keeps the admin
 * surface area on Oracle (single source of truth for auth).
 */
import { NextResponse } from "next/server";
import { getRequestContext } from "@cloudflare/next-on-pages";
import { oracleBase } from "@/lib/disputes";

export const runtime = "edge";
export const dynamic = "force-dynamic";

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

export async function GET(req: Request): Promise<Response> {
  let env: CloudflareEnv;
  try {
    env = getRequestContext().env;
  } catch {
    return NextResponse.json(
      { ok: false, error: "no_cloudflare_context" },
      { status: 503 }
    );
  }

  const admin = env.ADMIN_TOKEN;
  if (!admin) {
    return NextResponse.json(
      { ok: false, error: "admin_not_configured" },
      { status: 503 }
    );
  }

  const url = new URL(req.url);
  const headerToken =
    req.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? "";
  const queryToken = url.searchParams.get("token") ?? "";
  const supplied = headerToken || queryToken;
  if (!supplied || !timingSafeEqual(supplied, admin)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const internalToken = env.X402_INTERNAL_TOKEN;
  if (!internalToken) {
    return NextResponse.json(
      { ok: false, error: "internal_not_configured" },
      { status: 503 }
    );
  }

  const qs = url.search;
  const upstreamUrl = `${oracleBase(env)}/internal/disputes/list${qs || ""}`;
  try {
    const r = await fetch(upstreamUrl, {
      headers: { Authorization: `Bearer ${internalToken}` },
      signal: AbortSignal.timeout(8000),
    });
    const data = (await r.json().catch(() => null)) as unknown;
    if (!r.ok) {
      return NextResponse.json(
        { ok: false, error: `upstream_${r.status}`, upstream: data },
        { status: 502 }
      );
    }
    return NextResponse.json({ ok: true, ...(typeof data === "object" && data ? data : {}) });
  } catch (err) {
    console.error("[disputes/list] upstream failed:", err);
    return NextResponse.json(
      { ok: false, error: "upstream_unavailable" },
      { status: 502 }
    );
  }
}
