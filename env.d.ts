/// <reference types="@cloudflare/workers-types" />

// Augment the Cloudflare env shape that getRequestContext() returns so
// our route handlers see WAITLIST_KV (a KV namespace) and the same
// Telegram + admin secrets we configure in the Pages dashboard.
declare global {
  interface CloudflareEnv {
    WAITLIST_KV: KVNamespace;
    TELEGRAM_BOT_TOKEN?: string;
    TELEGRAM_CHAT_ID?: string;
    ADMIN_TOKEN?: string;
    // Shared secret + base URL for the Oracle FastAPI internal endpoints
    // (POST /api/v1/internal/disputes, GET /api/v1/internal/disputes/list).
    // Configured in the Cloudflare Pages dashboard, never sent to the client.
    X402_INTERNAL_TOKEN?: string;
    X402_INTERNAL_API?: string;
  }
}

export {};
