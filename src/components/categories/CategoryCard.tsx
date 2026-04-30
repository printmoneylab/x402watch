import Link from "next/link";
import { categoryAccent, prettyCategory, type CategoryRow } from "@/lib/categories";
import { LabelMiniBar } from "./LabelMiniBar";
import { cn } from "@/lib/utils";

const ACCENT_BORDER: Record<string, string> = {
  rose: "border-t-rose-500/70",
  emerald: "border-t-emerald-500/70",
  sky: "border-t-sky-500/70",
  violet: "border-t-violet-500/70",
  amber: "border-t-amber-500/60",
  slate: "border-t-slate-500/60",
};

const ACCENT_HOVER: Record<string, string> = {
  rose: "hover:shadow-[0_0_0_1px_rgba(244,63,94,0.35)]",
  emerald: "hover:shadow-[0_0_0_1px_rgba(16,185,129,0.35)]",
  sky: "hover:shadow-[0_0_0_1px_rgba(14,165,233,0.35)]",
  violet: "hover:shadow-[0_0_0_1px_rgba(139,92,246,0.35)]",
  amber: "hover:shadow-[0_0_0_1px_rgba(245,158,11,0.30)]",
  slate: "hover:shadow-[0_0_0_1px_rgba(148,163,184,0.25)]",
};

const fmtUsd = (n: number) =>
  n >= 1000
    ? `$${(n / 1000).toFixed(1)}K`
    : n >= 1
    ? `$${n.toFixed(2)}`
    : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

export function CategoryCard({ row }: { row: CategoryRow }) {
  const accent = categoryAccent(row.category);
  return (
    <Link
      href={`/categories/${encodeURIComponent(row.category)}`}
      className={cn(
        "group flex flex-col gap-3 rounded-lg border border-foreground/10 border-t-4 bg-foreground/[0.02] p-5 transition-shadow",
        ACCENT_BORDER[accent],
        ACCENT_HOVER[accent]
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold tracking-tight text-base leading-snug group-hover:text-foreground">
          {prettyCategory(row.category)}
        </h3>
        <span className="font-mono text-[10px] uppercase tracking-wider text-foreground/40">
          {row.category}
        </span>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-xs">
        <div className="flex flex-col">
          <dt className="text-foreground/50">Services</dt>
          <dd className="font-mono text-foreground/90">{fmtInt(row.services_count)}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-foreground/50">24h Vol</dt>
          <dd className="font-mono text-foreground/90">{fmtUsd(row.volume_24h)}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-foreground/50">Avg Price</dt>
          <dd className="font-mono text-foreground/90">
            {row.avg_price != null ? fmtUsd(row.avg_price) : "—"}
          </dd>
        </div>
      </dl>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-[10px] text-foreground/45 w-10">labels</span>
        <LabelMiniBar distribution={row.label_distribution} className="flex-1" />
        <span className="text-[10px] font-mono text-emerald-400 w-9 text-right">
          {row.real_volume_pct.toFixed(0)}%
        </span>
      </div>
    </Link>
  );
}
