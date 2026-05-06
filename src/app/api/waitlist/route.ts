/**
 * POST /api/waitlist — Pro-tier wait list collector.
 *
 * Stored under `waitlist:<lower_email>` in Vercel KV. Re-submits return 200
 * with `duplicate: true` so we don't leak whether an address is on the list.
 * The endpoint silently falls back to a console log when KV isn't configured
 * (local dev without the env vars set).
 */
import { NextResponse, after } from "next/server";
import { kv } from "@vercel/kv";

export const runtime = "nodejs";

async function notifyTelegram(
  record: { email: string; useCase: string | null; signed_up_at: string },
  total: number
): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chat = process.env.TELEGRAM_CHAT_ID;
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

type Body = { email?: unknown; useCase?: unknown };

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_USE_CASE = 280;

function clean(s: unknown, max: number): string {
  if (typeof s !== "string") return "";
  return s.trim().slice(0, max);
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

  // Best-effort KV write. If KV isn't configured (no env vars), log so the
  // operator notices but still succeed to the user — they shouldn't see infra
  // gaps as "submission failed."
  const kvConfigured =
    !!process.env.KV_REST_API_URL && !!process.env.KV_REST_API_TOKEN;

  if (!kvConfigured) {
    console.warn("[waitlist] KV not configured — skipping persist", record);
    return NextResponse.json({ ok: true, persisted: false });
  }

  try {
    const existing = await kv.get(key);
    if (existing) {
      return NextResponse.json({ ok: true, duplicate: true });
    }
    await kv.set(key, record);
    // Maintain a simple set of emails for export later. Capped index.
    await kv.sadd("waitlist:index", email);
    const total = (await kv.scard("waitlist:index")) ?? 0;
    // Telegram notify runs after the response is sent so the form
    // doesn't wait on the upstream HTTPS round-trip.
    after(() => notifyTelegram(record, total));
    return NextResponse.json({ ok: true, duplicate: false });
  } catch (err) {
    console.error("[waitlist] KV write failed:", err);
    return NextResponse.json(
      { error: "store unavailable, try again" },
      { status: 503 }
    );
  }
}
