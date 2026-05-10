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
  }
}

export {};
