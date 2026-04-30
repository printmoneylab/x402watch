import Link from "next/link";
import { ArrowUp } from "lucide-react";
import { prettyCategory } from "@/lib/categories";
import type { HotService, RecentNewService } from "@/lib/trends";
import { cn } from "@/lib/utils";

const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);
const fmtUsd = (n: number | null) => {
  if (n == null) return "—";
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}K`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(4)}`;
};

function fmtDate(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toISOString().slice(0, 10);
}

export function HotServices({ rows }: { rows: HotService[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-12 text-center text-sm text-foreground/55">
        No services with significant 24h activity surges.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-foreground/10">
      <table className="w-full text-sm">
        <thead className="bg-foreground/[0.04] text-foreground/70">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Service</th>
            <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Category</th>
            <th className="text-right px-3 py-2 font-medium">24h Tx</th>
            <th className="text-right px-3 py-2 font-medium">Δ Tx</th>
            <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">Real %</th>
            <th
              className={cn(
                "text-right px-3 py-2 font-medium hidden md:table-cell"
              )}
            >
              Wash %
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
            >
              <td className="px-3 py-2 max-w-xs">
                <Link
                  href={`/services/${r.id}`}
                  className="hover:text-accent block truncate"
                  title={r.name}
                >
                  {r.name || "(no name)"}
                </Link>
                <span className="text-[10px] font-mono text-foreground/35">
                  {r.chain}
                </span>
              </td>
              <td className="px-3 py-2 hidden md:table-cell text-xs text-foreground/65">
                {prettyCategory(r.category)}
              </td>
              <td className="px-3 py-2 text-right font-mono">{fmtInt(r.tx_24h)}</td>
              <td className="px-3 py-2 text-right">
                <span className="inline-flex items-center gap-0.5 font-mono text-emerald-400">
                  <ArrowUp className="size-3" />
                  {Math.abs(r.tx_change_pct).toFixed(0)}%
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono text-emerald-400 hidden sm:table-cell">
                {r.real_volume_pct.toFixed(0)}%
              </td>
              <td
                className={cn(
                  "px-3 py-2 text-right font-mono hidden md:table-cell",
                  r.wash_pct >= 50 ? "text-rose-400" : "text-foreground/55"
                )}
              >
                {r.wash_pct.toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RecentNewServices({ rows }: { rows: RecentNewService[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-8 text-center text-sm text-foreground/55">
        No new services in the last 24 hours.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-foreground/10">
      <table className="w-full text-sm">
        <thead className="bg-foreground/[0.04] text-foreground/70">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Name</th>
            <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Category</th>
            <th className="text-left px-3 py-2 font-medium hidden sm:table-cell">Chain</th>
            <th className="text-right px-3 py-2 font-medium">Price</th>
            <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">First seen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.id}
              className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
            >
              <td className="px-3 py-2 max-w-xs">
                <Link
                  href={`/services/${r.id}`}
                  className="hover:text-accent block truncate"
                  title={r.name}
                >
                  {r.name || "(no name)"}
                </Link>
              </td>
              <td className="px-3 py-2 hidden md:table-cell text-xs text-foreground/65">
                {prettyCategory(r.category)}
              </td>
              <td className="px-3 py-2 hidden sm:table-cell font-mono text-xs text-foreground/65">
                {r.chain}
              </td>
              <td className="px-3 py-2 text-right font-mono">{fmtUsd(r.price_amount)}</td>
              <td className="px-3 py-2 text-right font-mono text-xs text-foreground/55 hidden sm:table-cell">
                {fmtDate(r.first_seen)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
