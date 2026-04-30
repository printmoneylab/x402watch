import type { TopService } from "@/lib/categories";

const fmtUsd = (n: number | null) =>
  n == null ? "—"
  : n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

function hostname(url: string | null): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url.slice(0, 30);
  }
}

export function TopServicesTable({ services }: { services: TopService[] }) {
  if (!services.length) {
    return (
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-8 text-center text-sm text-foreground/55">
        No services with traffic in the last 30 days.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-foreground/10">
      <table className="w-full text-sm">
        <thead className="bg-foreground/[0.04] text-foreground/70">
          <tr>
            <th className="text-left px-3 py-2 font-medium w-10">#</th>
            <th className="text-left px-3 py-2 font-medium">Service</th>
            <th className="text-right px-3 py-2 font-medium">Price</th>
            <th className="text-right px-3 py-2 font-medium">30d Tx</th>
            <th className="text-right px-3 py-2 font-medium hidden sm:table-cell">30d Volume</th>
            <th className="text-right px-3 py-2 font-medium">Real %</th>
            <th className="text-right px-3 py-2 font-medium hidden md:table-cell">Wash %</th>
          </tr>
        </thead>
        <tbody>
          {services.map((s, i) => (
            <tr
              key={s.id}
              className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors"
            >
              <td className="px-3 py-2 font-mono text-foreground/45">{i + 1}</td>
              <td className="px-3 py-2 max-w-xs">
                <div className="truncate" title={s.name}>
                  {s.name || "(no name)"}
                </div>
                {s.resource_url && (
                  <div className="text-[11px] font-mono text-foreground/40 truncate">
                    {hostname(s.resource_url)}
                  </div>
                )}
              </td>
              <td className="px-3 py-2 text-right font-mono">{fmtUsd(s.price)}</td>
              <td className="px-3 py-2 text-right font-mono">{fmtInt(s.tx_30d)}</td>
              <td className="px-3 py-2 text-right font-mono hidden sm:table-cell">
                {fmtUsd(s.volume_30d)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-emerald-400">
                {s.real_pct.toFixed(0)}%
              </td>
              <td className="px-3 py-2 text-right font-mono text-rose-400 hidden md:table-cell">
                {s.wash_pct.toFixed(0)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
