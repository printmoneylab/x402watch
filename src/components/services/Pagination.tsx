"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

function pageWindow(current: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const out: (number | "…")[] = [1];
  const left = Math.max(2, current - 1);
  const right = Math.min(total - 1, current + 1);
  if (left > 2) out.push("…");
  for (let i = left; i <= right; i++) out.push(i);
  if (right < total - 1) out.push("…");
  out.push(total);
  return out;
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
  if (totalPages <= 1) return null;
  const items = pageWindow(page, totalPages);

  return (
    <nav className="flex items-center justify-between gap-2 mt-6 select-none" aria-label="Pagination">
      <button
        type="button"
        onClick={() => onChange(page - 1)}
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
              onClick={() => onChange(it)}
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
        {page} / {totalPages}
      </span>

      <button
        type="button"
        onClick={() => onChange(page + 1)}
        disabled={page >= totalPages}
        className="inline-flex items-center gap-1 h-9 px-3 rounded-md text-sm border border-foreground/15 hover:bg-foreground/5 disabled:opacity-30 disabled:pointer-events-none"
      >
        <span className="hidden sm:inline">Next</span>
        <ChevronRight className="size-4" />
      </button>
    </nav>
  );
}
