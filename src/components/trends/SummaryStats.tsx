import { ArrowDown, ArrowUp } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TrendsSummary } from "@/lib/trends";

const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);
const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;

function ChangeBadge({ pct }: { pct: number }) {
  if (!Number.isFinite(pct) || pct === 0) {
    return <span className="text-foreground/40 font-mono text-xs">±0%</span>;
  }
  const up = pct > 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono text-xs",
        up ? "text-emerald-400" : "text-rose-400"
      )}
    >
      {up ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
      {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

export function SummaryStats({ summary }: { summary: TrendsSummary }) {
  const stats = [
    {
      label: "New services (24h)",
      value: fmtInt(summary.new_services_24h),
      change: summary.new_services_change_pct,
      sub: `vs ${fmtInt(summary.new_services_prev_24h)} prev 24h`,
    },
    {
      label: "Total tx (24h)",
      value: fmtInt(summary.total_tx_24h),
      change: null,
      sub: null,
    },
    {
      label: "Total volume (24h)",
      value: fmtUsd(summary.total_volume_24h),
      change: null,
      sub: null,
    },
    {
      label: "Active buyers (24h)",
      value: fmtInt(summary.active_buyers_24h),
      change: null,
      sub: null,
    },
  ];
  return (
    <dl className="grid grid-cols-2 sm:grid-cols-4 gap-y-6 gap-x-6">
      {stats.map((s) => (
        <div key={s.label} className="flex flex-col gap-1">
          <dt className="order-2 text-[11px] uppercase tracking-wide text-foreground/55">
            {s.label}
          </dt>
          <dd className="order-1 font-mono text-2xl sm:text-3xl font-medium tracking-tight">
            {s.value}
          </dd>
          {s.change != null && (
            <dd className="order-3 flex items-center gap-2 text-xs">
              <ChangeBadge pct={s.change} />
              {s.sub && <span className="text-foreground/45">{s.sub}</span>}
            </dd>
          )}
        </div>
      ))}
    </dl>
  );
}
