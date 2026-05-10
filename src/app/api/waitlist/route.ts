/**
 * POST /api/waitlist — Pro-tier wait list collector.
 *
 * Stored in Cloudflare Workers KV under `waitlist:<lower_email>`.
 * Re-submits return 200 with `duplicate: true` so we don't leak whether
 * an address is on the list. Telegram notification fires after the
 * response via next/server's after().
 *
 * Migrated from Vercel KV (Upstash) — KV is now a CF Workers binding
 * accessed via @cloudflare/next-on-pages getRequestContext().
 */
import { NextResponse, after } from "next/server";
import { getRequestContext } from "@cloudflare/next-on-pages";

export const runtime = "edge";

type Body = { email?: unknown; useCase?: unknown };

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_USE_CASE = 280;

function clean(s: unknown, max: number): string {
  if (typeof s !== "string") return "";
  return s.trim().slice(0, max);
}

async function notifyTelegram(
  env: CloudflareEnv,
  record: { email: string; useCase: string | null; signed_up_at: string },
  total: number
): Promise<void> {
  const token = env.TELEGRAM_BOT_TOKEN;
  const chat = env.TELEGRAM_CHAT_ID;
  if (!token || !chat) {
    console.warn("[waitlist] telegram env vars missing — skipping notify");
    return;
  }
  const text = [
    "📋 New x402watch wait list signup",
    `Email: ${record.email}`,
    `Use case: ${record.useCase || "(none)"}`,
    `Total signups: ${total}`,
  ].join("\n");
  try {
    const r = await fetch(
      `https://api.telegram.org/bot${token}/sendMessage`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chat, text }),
        signal: AbortSignal.timeout(5000),
      }
    );
    if (!r.ok) {
      console.error("[waitlist] telegram non-200:", r.status, await r.text());
    }
  } catch (err) {
    console.error("[waitlist] telegram failed:", err);
  }
}

export async function POST(req: Request): Promise<Response> {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ error: "invalid JSON" }, { status: 400 });
  }

  const email = clean(body.email, 254).toLowerCase();
  const useCase = clean(body.useCase, MAX_USE_CASE);

  if (!email) {
    return NextResponse.json({ error: "email is required" }, { status: 400 });
  }
  if (!EMAIL_RE.test(email)) {
    return NextResponse.json({ error: "invalid email" }, { status: 400 });
  }

  const key = `waitlist:${email}`;
  const record = {
    email,
    useCase: useCase || null,
    signed_up_at: new Date().toISOString(),
  };

  let env: CloudflareEnv;
  try {
    env = getRequestContext().env;
  } catch (err) {
    // Local dev outside `wrangler pages dev` — log + succeed without persist.
    console.warn("[waitlist] no Cloudflare context:", err);
    return NextResponse.json({ ok: true, persisted: false });
  }

  if (!env.WAITLIST_KV) {
    console.warn("[waitlist] WAITLIST_KV binding missing — skipping persist");
    return NextResponse.json({ ok: true, persisted: false });
  }

  try {
    const existing = await env.WAITLIST_KV.get(key);
    if (existing !== null) {
      return NextResponse.json({ ok: true, duplicate: true });
    }
    await env.WAITLIST_KV.put(key, JSON.stringify(record));

    // Lightweight count via KV list. Limited to 1000 per page; for the
    // notification we just want a ballpark, so stop at the first page.
    const list = await env.WAITLIST_KV.list({ prefix: "waitlist:", limit: 1000 });
    const total = list.keys.length;

    after(() => notifyTelegram(env, record, total));
    return NextResponse.json({ ok: true, duplicate: false });
  } catch (err) {
    console.error("[waitlist] KV write failed:", err);
    return NextResponse.json(
      { error: "store unavailable, try again" },
      { status: 503 }
    );
  }
}
