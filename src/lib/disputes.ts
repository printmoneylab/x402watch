/**
 * Dispute-submission helpers shared by the /api/disputes Edge routes.
 * The Cloudflare Pages route is a thin proxy in front of the Oracle
 * FastAPI internal endpoint — it validates the input, rate-limits per
 * IP via Workers KV, then forwards to Oracle with a shared secret. The
 * authoritative store lives on Oracle (label_disputes + recompute_queue
 * tables) so the same SQL is reused by the daily labeller's
 * process_recompute_queue() worker.
 */

export const ALL_LABELS = [
  "organic_user",
  "self_test",
  "developer",
  "suspected_wash",
  "ai_agent",
  "analytics_bot",
  "exchange_user",
  "verifier",
  "owner_test",
  "unlabeled",
] as const;
export type DisputeLabel = (typeof ALL_LABELS)[number];

export const REASON_MIN = 32;
export const REASON_MAX = 1000;

/** EVM `0x...` (40 hex) or Solana base58 (32-44 chars, no 0/O/I/l). */
const EVM_RE = /^0x[a-fA-F0-9]{40}$/;
const SOL_RE = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;
export function isWalletAddress(s: string): boolean {
  return EVM_RE.test(s) || SOL_RE.test(s);
}

export type DisputeInput = {
  buyer_address: string;
  seller_address?: string;
  reporter_address?: string;
  reason: string;
  current_label: string;
  current_confidence?: number;
};

export type DisputeValidationError =
  | "invalid_buyer"
  | "invalid_seller"
  | "invalid_reporter"
  | "invalid_label"
  | "reason_too_short"
  | "reason_too_long";

export type ValidationResult =
  | { ok: true; clean: Required<Pick<DisputeInput, "buyer_address" | "reason" | "current_label">> & DisputeInput }
  | { ok: false; error: DisputeValidationError };

export function validateDispute(body: Partial<DisputeInput>): ValidationResult {
  const buyer = typeof body.buyer_address === "string" ? body.buyer_address.trim() : "";
  if (!isWalletAddress(buyer)) return { ok: false, error: "invalid_buyer" };

  const seller =
    typeof body.seller_address === "string" && body.seller_address.trim() !== ""
      ? body.seller_address.trim()
      : undefined;
  if (seller !== undefined && !isWalletAddress(seller)) {
    return { ok: false, error: "invalid_seller" };
  }

  const reporter =
    typeof body.reporter_address === "string" && body.reporter_address.trim() !== ""
      ? body.reporter_address.trim()
      : undefined;
  if (reporter !== undefined && !isWalletAddress(reporter)) {
    return { ok: false, error: "invalid_reporter" };
  }

  const label = typeof body.current_label === "string" ? body.current_label.trim() : "";
  if (!(ALL_LABELS as readonly string[]).includes(label)) {
    return { ok: false, error: "invalid_label" };
  }

  const reason = typeof body.reason === "string" ? body.reason.trim() : "";
  if (reason.length < REASON_MIN) return { ok: false, error: "reason_too_short" };
  if (reason.length > REASON_MAX) return { ok: false, error: "reason_too_long" };

  return {
    ok: true,
    clean: {
      buyer_address: buyer,
      seller_address: seller,
      reporter_address: reporter,
      reason,
      current_label: label,
      current_confidence:
        typeof body.current_confidence === "number" && Number.isFinite(body.current_confidence)
          ? body.current_confidence
          : undefined,
    },
  };
}

/** Extract a best-effort client IP from CF / proxy headers. */
export function clientIp(req: Request): string {
  const cf =
    req.headers.get("cf-connecting-ip") ||
    req.headers.get("x-real-ip") ||
    req.headers.get("x-forwarded-for")?.split(",")[0].trim();
  return (cf || "unknown").slice(0, 64);
}

/**
 * Increment-and-check rate limit window stored in Workers KV.
 * Returns the current count after incrementing, plus a `limited` flag.
 * Different scopes use different TTLs and limits — caller decides.
 */
export async function bumpRateLimit(
  kv: KVNamespace,
  scope: string,
  key: string,
  limit: number,
  ttlSeconds: number
): Promise<{ count: number; limited: boolean }> {
  const k = `dispute_rl:${scope}:${key}`;
  const prev = await kv.get(k);
  const count = prev ? parseInt(prev, 10) + 1 : 1;
  // Workers KV doesn't have INCR; we re-PUT with the original TTL window.
  // Slight drift is acceptable for rate limiting.
  await kv.put(k, String(count), { expirationTtl: ttlSeconds });
  return { count, limited: count > limit };
}

/** A `dispute_ban:<ip>` key shortcuts everything when set. */
export async function isBanned(kv: KVNamespace, ip: string): Promise<boolean> {
  return (await kv.get(`dispute_ban:${ip}`)) !== null;
}

export async function banIp(kv: KVNamespace, ip: string, ttl = 86400): Promise<void> {
  await kv.put(`dispute_ban:${ip}`, "1", { expirationTtl: ttl });
}

export const ORACLE_INTERNAL_FALLBACK =
  "https://api.x402.printmoneylab.com/api/v1";

export function oracleBase(env: CloudflareEnv): string {
  return env.X402_INTERNAL_API || ORACLE_INTERNAL_FALLBACK;
}
