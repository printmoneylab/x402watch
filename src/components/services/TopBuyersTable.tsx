import type { ServiceDetail } from "@/lib/services";
import { LABEL_COLOR_TW } from "@/lib/categories";
import { cn } from "@/lib/utils";

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

function shortAddr(a: string): string {
  if (a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

export function TopBuyersTable({
  buyers,
}: {
  buyers: ServiceDetail["top_buyers"];
}) {
  if (!buyers.length) {
    return (
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-8 text-center text-sm text-foreground/55">
        No buyers recorded yet.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-foreground/10">
      <table className="w-full text-sm">
        <thead className="bg-foreground/[0.04] text-foreground/70">
          <tr>
            <th className="text-left px-3 py-2 font-medium w-10">#</th>
            <th className="text-left px-3 py-2 font-medium">Buyer</th>
            <th className="text-left px-3 py-2 font-medium">Label</th>
            <th className="text-right px-3 py-2 font-medium">Tx</th>
            <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">Volume</th>
            <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {buyers.map((b, i) => {
            const swatch = b.label
              ? LABEL_COLOR_TW[b.label] ?? "bg-zinc-700"
              : "bg-zinc-700";
            return (
              <tr
                key={b.buyer_address}
                className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
              >
                <td className="px-3 py-2 font-mono text-foreground/45">{i + 1}</td>
                <td className="px-3 py-2">
                  <span
                    className="font-mono text-foreground/85"
                    title={b.buyer_address}
                  >
                    {shortAddr(b.buyer_address)}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 text-xs">
                    <span className={cn("size-2 rounded-full", swatch)} />
                    {b.label ?? "(unlabeled)"}
                  </span>
                </td>
                <td className="px-3 py-2 text-right font-mono">{fmtInt(b.tx_count)}</td>
                <td className="px-3 py-2 text-right font-mono hidden sm:table-cell">
                  {fmtUsd(b.volume)}
                </td>
                <td className="px-3 py-2 text-right font-mono hidden md:table-cell text-foreground/60">
                  {b.confidence != null ? b.confidence.toFixed(2) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
