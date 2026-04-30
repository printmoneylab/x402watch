"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { prettyCategory } from "@/lib/categories";
import type { CategoryMover } from "@/lib/trends";
import { cn } from "@/lib/utils";

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

type SortBy = "volume_change" | "tx_change" | "volume" | "tx";

function changeCell(pct: number) {
  if (!Number.isFinite(pct) || pct === 0) {
    return <span className="font-mono text-foreground/40">±0%</span>;
  }
  const up = pct > 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono",
        up ? "text-emerald-400" : "text-rose-400"
      )}
    >
      {up ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
      {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

export function CategoryMovers({ rows }: { rows: CategoryMover[] }) {
  const [sortBy, setSortBy] = useState<SortBy>("volume_change");

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-12 text-center text-sm text-foreground/55">
        No category movement data yet.
      </div>
    );
  }

  const sorted = [...rows].sort((a, b) => {
    switch (sortBy) {
      case "volume_change": return b.change_pct - a.change_pct;
      case "tx_change":     return b.tx_change_pct - a.tx_change_pct;
      case "volume":        return b.volume_24h - a.volume_24h;
      case "tx":            return b.tx_24h - a.tx_24h;
    }
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-foreground/10">
      <table className="w-full text-sm">
        <thead className="bg-foreground/[0.04] text-foreground/70">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Category</th>
            <th
              className="text-right px-3 py-2 font-medium cursor-pointer hover:text-foreground"
              onClick={() => setSortBy("volume")}
              aria-sort={sortBy === "volume" ? "descending" : "none"}
            >
              24h Volume
            </th>
            <th
              className="text-right px-3 py-2 font-medium cursor-pointer hover:text-foreground"
              onClick={() => setSortBy("volume_change")}
              aria-sort={sortBy === "volume_change" ? "descending" : "none"}
            >
              Δ Volume
            </th>
            <th
              className="text-right px-3 py-2 font-medium hidden sm:table-cell cursor-pointer hover:text-foreground"
              onClick={() => setSortBy("tx")}
              aria-sort={sortBy === "tx" ? "descending" : "none"}
            >
              24h Tx
            </th>
            <th
              className="text-right px-3 py-2 font-medium hidden sm:table-cell cursor-pointer hover:text-foreground"
              onClick={() => setSortBy("tx_change")}
              aria-sort={sortBy === "tx_change" ? "descending" : "none"}
            >
              Δ Tx
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.category}
              className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
            >
              <td className="px-3 py-2">
                <Link
                  href={`/categories/${encodeURIComponent(r.category)}`}
                  className="hover:text-accent"
                >
                  {prettyCategory(r.category)}
                </Link>
                <span className="ml-2 font-mono text-[10px] text-foreground/40">
                  {r.category}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono">{fmtUsd(r.volume_24h)}</td>
              <td className="px-3 py-2 text-right">{changeCell(r.change_pct)}</td>
              <td className="px-3 py-2 text-right font-mono hidden sm:table-cell">
                {fmtInt(r.tx_24h)}
              </td>
              <td className="px-3 py-2 text-right hidden sm:table-cell">
                {changeCell(r.tx_change_pct)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
