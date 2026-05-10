/**
 * GET /api/waitlist/count — admin-only.
 *
 * Auth via either:
 *   Authorization: Bearer <ADMIN_TOKEN>
 * or
 *   ?token=<ADMIN_TOKEN>
 *
 * Returns total signups + the 10 most recent records (sorted by
 * signed_up_at desc). Uses Cloudflare Workers KV `list({ prefix })`
 * + `get` per key (no SMEMBERS in CF KV).
 */
import { NextResponse } from "next/server";
import { getRequestContext } from "@cloudflare/next-on-pages";

export const runtime = "edge";
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
  let env: CloudflareEnv;
  try {
    env = getRequestContext().env;
  } catch {
    return NextResponse.json(
      { error: "Cloudflare context unavailable (running outside Pages?)" },
      { status: 503 }
    );
  }

  const expected = env.ADMIN_TOKEN;
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

  if (!env.WAITLIST_KV) {
    return NextResponse.json({
      total: 0,
      recent: [],
      note: "WAITLIST_KV binding missing",
    });
  }

  // Walk the prefix until the cursor is exhausted (or we hit a sane cap).
  // CF KV list is paginated; default page is 1000. For now we cap at
  // 5 pages = 5000 emails — beyond that, switch to a separate counter key.
  const allKeys: string[] = [];
  let cursor: string | undefined = undefined;
  let pages = 0;
  while (pages < 5) {
    const resp = (await env.WAITLIST_KV.list({
      prefix: "waitlist:",
      cursor,
    })) as { keys: { name: string }[]; list_complete: boolean; cursor?: string };
    for (const k of resp.keys) allKeys.push(k.name);
    if (resp.list_complete) break;
    cursor = resp.cursor;
    pages += 1;
  }

  const total = allKeys.length;
  if (total === 0) {
    return NextResponse.json({ total: 0, recent: [] });
  }

  // Fetch every record. For the recent-10 use case this is fine up to
  // a few thousand keys; trade up to a separate "recent" list when the
  // wait list grows beyond that.
  const records = await Promise.all(
    allKeys.map(async (k) => {
      const raw = await env.WAITLIST_KV.get(k);
      if (!raw) return null;
      try {
        return JSON.parse(raw) as WaitlistRecord;
      } catch {
        return null;
      }
    })
  );
  const valid = records.filter(
    (r): r is WaitlistRecord =>
      !!r && typeof r.signed_up_at === "string"
  );
  // ISO 8601 sorts lexicographically — newest first.
  valid.sort((a, b) => b.signed_up_at.localeCompare(a.signed_up_at));

  return NextResponse.json({
    total,
    recent: valid.slice(0, 10),
  });
}
