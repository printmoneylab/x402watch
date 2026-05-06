/**
 * GET /api/waitlist/count — admin-only.
 *
 * Auth: provide ADMIN_TOKEN as either
 *   Authorization: Bearer <token>
 * or
 *   ?token=<token>
 *
 * Returns the total signup count plus the 10 most recent records (sorted
 * by signed_up_at desc).
 */
import { NextResponse } from "next/server";
import { kv } from "@vercel/kv";

export const runtime = "nodejs";
// Always evaluate fresh — the count moves.
export const dynamic = "force-dynamic";

type WaitlistRecord = {
  email: string;
  useCase: string | null;
  signed_up_at: string;
};

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

export async function GET(req: Request): Promise<Response> {
  const expected = process.env.ADMIN_TOKEN;
  if (!expected) {
    return NextResponse.json(
      { error: "ADMIN_TOKEN not configured" },
      { status: 503 }
    );
  }

  const url = new URL(req.url);
  const auth = req.headers.get("authorization") || "";
  const headerToken = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  const queryToken = (url.searchParams.get("token") || "").trim();
  const provided = headerToken || queryToken;
  if (!provided || !timingSafeEqual(provided, expected)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  if (!process.env.KV_REST_API_URL) {
    return NextResponse.json({
      total: 0,
      recent: [],
      note: "KV not configured",
    });
  }

  const total = (await kv.scard("waitlist:index")) ?? 0;
  if (total === 0) {
    return NextResponse.json({ total: 0, recent: [] });
  }

  const emails = (await kv.smembers("waitlist:index")) as string[];
  const records = await Promise.all(
    emails.map((email) => kv.get<WaitlistRecord>(`waitlist:${email}`))
  );
  const valid = records.filter(
    (r): r is WaitlistRecord =>
      !!r && typeof r === "object" && typeof r.signed_up_at === "string"
  );
  // Newest first by ISO timestamp string compare (ISO 8601 sorts lexically).
  valid.sort((a, b) => b.signed_up_at.localeCompare(a.signed_up_at));

  return NextResponse.json({
    total,
    recent: valid.slice(0, 10),
  });
}
