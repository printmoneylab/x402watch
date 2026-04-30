"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

function pageWindow(current: number, total: number): (number | "…")[] {
  // Show up to 9 numbers (incl. first/last + 2 ellipses + 5 middle).
  if (total <= 9) return Array.from({ length: total }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const left = Math.max(2, current - 2);
  const right = Math.min(total - 1, current + 2);
  if (left > 2) out.push("…");
  for (let i = left; i <= right; i++) out.push(i);
  if (right < total - 1) out.push("…");
  out.push(total);
  return out;
}

function scrollToTop() {
  if (typeof window === "undefined") return;
  // Smooth scroll to top after a page change. The header is sticky so
  // the user lands at the natural top of the next page's results.
  window.scrollTo({ top: 0, behavior: "smooth" });
}

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}) {
  const [jumpInput, setJumpInput] = useState("");

  if (totalPages <= 1) return null;

  const go = (n: number) => {
    if (!Number.isFinite(n)) return;
    const clamped = Math.max(1, Math.min(totalPages, Math.floor(n)));
    if (clamped === page) return;
    onChange(clamped);
    scrollToTop();
  };

  const submitJump = () => {
    const n = parseInt(jumpInput, 10);
    if (!Number.isFinite(n)) return;
    if (n < 1 || n > totalPages) return;
    setJumpInput("");
    go(n);
  };

  const items = pageWindow(page, totalPages);

  return (
    <nav
      className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mt-6 select-none"
      aria-label="Pagination"
    >
      <div className="flex items-center justify-between gap-2 sm:flex-1">
        <button
          type="button"
          onClick={() => go(page - 1)}
          disabled={page <= 1}
          className="inline-flex items-center gap-1 h-9 px-3 rounded-md text-sm border border-foreground/15 hover:bg-foreground/5 disabled:opacity-30 disabled:pointer-events-none"
        >
          <ChevronLeft className="size-4" />
          <span className="hidden sm:inline">Prev</span>
        </button>

        <div className="hidden sm:flex items-center gap-1">
          {items.map((it, idx) =>
            it === "…" ? (
              <span key={`g-${idx}`} className="px-2 text-foreground/40">…</span>
            ) : (
              <button
                key={it}
                type="button"
                onClick={() => go(it)}
                aria-current={it === page ? "page" : undefined}
                className={cn(
                  "h-9 min-w-9 px-3 rounded-md text-sm",
                  it === page
                    ? "bg-foreground/10 text-foreground border border-foreground/20"
                    : "hover:bg-foreground/5 text-foreground/70"
                )}
              >
                {it}
              </button>
            )
          )}
        </div>

        <span className="sm:hidden text-xs font-mono text-foreground/55">
          Page {page} of {totalPages}
        </span>

        <button
          type="button"
          onClick={() => go(page + 1)}
          disabled={page >= totalPages}
          className="inline-flex items-center gap-1 h-9 px-3 rounded-md text-sm border border-foreground/15 hover:bg-foreground/5 disabled:opacity-30 disabled:pointer-events-none"
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="size-4" />
        </button>
      </div>

      <div className="flex items-center justify-end gap-1.5 text-xs text-foreground/65">
        <span className="text-foreground/45">Go to</span>
        <input
          type="number"
          inputMode="numeric"
          min={1}
          max={totalPages}
          value={jumpInput}
          onChange={(e) => setJumpInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              submitJump();
            }
          }}
          placeholder={String(page)}
          aria-label={`Jump to page (1 to ${totalPages})`}
          className="w-16 h-8 px-2 rounded-md bg-foreground/5 border border-foreground/15 text-sm font-mono placeholder:text-foreground/35 focus:outline-none focus:ring-2 focus:ring-accent/40 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <button
          type="button"
          onClick={submitJump}
          disabled={!jumpInput}
          className="h-8 px-2.5 rounded-md text-sm border border-foreground/15 text-foreground/75 hover:bg-foreground/5 hover:text-foreground disabled:opacity-30 disabled:pointer-events-none"
        >
          Go
        </button>
      </div>
    </nav>
  );
}
