"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { categoryAccent, prettyCategory } from "@/lib/categories";
import { LabelMiniBar } from "@/components/categories/LabelMiniBar";
import type { ServiceRow } from "@/lib/services";
import { cn } from "@/lib/utils";

const ACCENT_BORDER: Record<string, string> = {
  rose: "border-l-rose-500/70",
  emerald: "border-l-emerald-500/70",
  sky: "border-l-sky-500/70",
  violet: "border-l-violet-500/70",
  amber: "border-l-amber-500/60",
  slate: "border-l-slate-500/60",
};

function fmtUsd(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}K`;
  if (n >= 1) return `$${n.toFixed(2)}`;
  return `$${n.toFixed(4)}`;
}
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

function shortAddr(addr: string): string {
  if (!addr) return "";
  if (addr.length <= 12) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

export function ServiceCard({
  row,
  sellerDotClass,
}: {
  row: ServiceRow;
  sellerDotClass?: string;
}) {
  const accent = categoryAccent(row.category);
  const router = useRouter();

  const onSellerClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Filter the list to this seller. The API's `search` field already
    // matches the seller address, so this scopes the page without needing
    // a separate query param.
    const params = new URLSearchParams();
    params.set("search", row.seller_address);
    router.push(`/services?${params.toString()}`, { scroll: false });
  };

  return (
    <Link
      href={`/services/${row.id}`}
      className={cn(
        "group flex flex-col gap-3 rounded-lg border border-foreground/10 border-l-4 bg-foreground/[0.02] p-5 transition-shadow hover:shadow-[0_0_0_1px_rgba(255,255,255,0.10)]",
        ACCENT_BORDER[accent]
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-full border border-foreground/15 bg-foreground/[0.04] px-2 py-0.5 text-[10px] font-mono text-foreground/70">
            {prettyCategory(row.category)}
          </span>
          <span className="inline-flex items-center rounded-full border border-foreground/15 bg-foreground/[0.04] px-2 py-0.5 text-[10px] font-mono text-foreground/70">
            {row.chain}
          </span>
        </div>
        <span className="font-mono text-xs text-foreground/45">#{row.id}</span>
      </div>

      <h3
        className="font-semibold tracking-tight text-base leading-snug line-clamp-2 group-hover:text-foreground"
        title={row.name}
      >
        {row.name || "(no name)"}
      </h3>
      {row.description && row.description !== row.name && (
        <p className="text-xs text-foreground/55 line-clamp-2 leading-relaxed">
          {row.description}
        </p>
      )}

      <dl className="grid grid-cols-3 gap-2 text-xs mt-1">
        <div className="flex flex-col">
          <dt className="text-foreground/45">Price</dt>
          <dd className="font-mono text-foreground/85">{fmtUsd(row.price_amount)}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-foreground/45">24h Tx</dt>
          <dd className="font-mono text-foreground/85">{fmtInt(row.tx_24h)}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-foreground/45">24h Vol</dt>
          <dd className="font-mono text-foreground/85">{fmtUsd(row.volume_24h)}</dd>
        </div>
      </dl>

      <div className="mt-1">
        <LabelMiniBar distribution={row.label_distribution} />
        <div className="flex items-center justify-between text-[11px] mt-2">
          <span className="text-emerald-400 font-mono">
            real {row.real_volume_pct.toFixed(0)}%
          </span>
          <span
            className={cn(
              "font-mono",
              row.wash_pct >= 50
                ? "text-rose-400"
                : row.wash_pct > 0
                ? "text-rose-300/70"
                : "text-foreground/40"
            )}
          >
            wash {row.wash_pct.toFixed(0)}%
          </span>
        </div>
      </div>

      {row.seller_address && (
        <div className="mt-2 pt-2 border-t border-foreground/5 flex items-center gap-1.5 text-[11px] text-foreground/45">
          <span className="text-foreground/35">by</span>
          {sellerDotClass && (
            <span
              className={cn("inline-block size-1.5 rounded-full", sellerDotClass)}
              aria-hidden
            />
          )}
          <button
            type="button"
            onClick={onSellerClick}
            title={`Filter by seller ${row.seller_address}`}
            className="font-mono text-foreground/65 hover:text-accent hover:underline truncate"
          >
            {shortAddr(row.seller_address)}
          </button>
        </div>
      )}
    </Link>
  );
}
