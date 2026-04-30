"use client";

import { useSyncExternalStore } from "react";

/**
 * Renders a timestamp as `Updated <relative> · <local time> your local time`,
 * auto-refreshing every minute. Uses useSyncExternalStore so the server
 * snapshot is `null` (no client time available) and the client subscribes
 * to a setInterval ticker — no hydration mismatch, no setState-in-effect.
 */

function subscribe(cb: () => void) {
  const id = setInterval(cb, 60_000);
  return () => clearInterval(id);
}
function getNow(): number {
  return Date.now();
}
function getServerSnapshot(): null {
  return null;
}

function relativeFromNow(thenMs: number, nowMs: number): string {
  const seconds = Math.round((nowMs - thenMs) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes !== 1 ? "s" : ""} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours !== 1 ? "s" : ""} ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} day${days !== 1 ? "s" : ""} ago`;
  return new Date(thenMs).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function localTimeShort(d: Date): string {
  // Browser-local timezone with explicit en-US locale so the format is
  // predictable across machines (Apr 30, 14:30 — 24h clock).
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function isoToCompactUtc(iso: string): string {
  // SSR-safe fallback: deterministic UTC string with no client-locale
  // dependence (matches whatever the server renders byte-for-byte).
  if (!iso) return "—";
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}

export function RelativeTime({
  iso,
  className,
}: {
  iso: string;
  className?: string;
}) {
  const now = useSyncExternalStore(subscribe, getNow, getServerSnapshot);

  if (!iso) {
    return <span className={className}>Updated —</span>;
  }
  const thenMs = new Date(iso).getTime();
  if (!Number.isFinite(thenMs)) {
    return <span className={className}>Updated —</span>;
  }

  if (now == null) {
    // SSR + first client paint: deterministic UTC string. Once the
    // store subscribes (post-hydration) we swap to the relative form.
    return (
      <span className={className} title={iso}>
        Updated {isoToCompactUtc(iso)}
      </span>
    );
  }

  return (
    <span className={className} title={new Date(iso).toISOString()}>
      Updated {relativeFromNow(thenMs, now)} ·{" "}
      {localTimeShort(new Date(iso))} your local time
    </span>
  );
}
