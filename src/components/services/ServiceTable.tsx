import Link from "next/link";
import { prettyCategory } from "@/lib/categories";
import { LabelMiniBar } from "@/components/categories/LabelMiniBar";
import type { ServiceRow } from "@/lib/services";
import { cn } from "@/lib/utils";

function fmtUsd(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}K`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(4)}`;
}
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

export function ServiceTable({
  rows,
  pageStart,
}: {
  rows: ServiceRow[];
  pageStart: number;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-foreground/10">
      <table className="w-full text-sm">
        <thead className="bg-foreground/[0.04] text-foreground/70">
          <tr>
            <th className="text-left px-3 py-2 font-medium w-12">#</th>
            <th className="text-left px-3 py-2 font-medium">Name</th>
            <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Category</th>
            <th className="text-left px-3 py-2 font-medium hidden md:table-cell">Chain</th>
            <th className="text-right px-3 py-2 font-medium">Price</th>
            <th className="text-right px-3 py-2 font-medium">24h Tx</th>
            <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">24h Vol</th>
            <th className="text-right px-3 py-2 font-medium hidden lg:table-cell">Total Tx</th>
            <th className="text-right px-3 py-2 font-medium">Real %</th>
            <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Wash %</th>
            <th className="text-left px-3 py-2 font-medium hidden xl:table-cell w-32">Labels</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr
              key={r.id}
              className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
            >
              <td className="px-3 py-2 font-mono text-foreground/45">{pageStart + i}</td>
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
              <td className="px-3 py-2 hidden md:table-cell font-mono text-xs text-foreground/65">
                {r.chain}
              </td>
              <td className="px-3 py-2 text-right font-mono">{fmtUsd(r.price_amount)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtInt(r.tx_24h)}</td>
              <td className="px-3 py-2 text-right font-mono hidden sm:table-cell">
                {fmtUsd(r.volume_24h)}
              </td>
              <td className="px-3 py-2 text-right font-mono hidden lg:table-cell">
                {fmtInt(r.tx_total)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-emerald-400">
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
              <td className="px-3 py-2 hidden xl:table-cell w-32">
                <LabelMiniBar distribution={r.label_distribution} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
