/**
 * Top buyers for a service detail page. Splits rows into two groups:
 *  - Main table: external buyers (organic / ai_agent / suspected_wash / etc.)
 *  - Collapsible "Operator self-tests": owner_test labelled buyers, hidden
 *    by default. These are excluded from real_volume_pct/wash_pct denominators
 *    upstream (see derive_global.update_service_stats_v2), so surfacing them
 *    separately keeps the public table honest.
 *
 * Uses LabelBadge for confidence-band-aware rendering.
 */
import type { ServiceDetail } from "@/lib/services";
import { LabelBadge, type BuyerLabel } from "@/components/common/LabelBadge";

const fmtUsd = (n: number) =>
  n >= 1000 ? `$${(n / 1000).toFixed(1)}K`
  : n >= 1 ? `$${n.toFixed(2)}`
  : `$${n.toFixed(4)}`;
const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

function shortAddr(a: string): string {
  if (a.length < 12) return a;
  return `${a.slice(0, 6)}…${a.slice(-4)}`;
}

type Buyer = ServiceDetail["top_buyers"][number];

function BuyerRow({
  buyer,
  rank,
  sellerAddress,
}: {
  buyer: Buyer;
  rank: number;
  sellerAddress?: string;
}) {
  const conf = buyer.confidence;
  return (
    <tr className="border-t border-foreground/5 hover:bg-foreground/[0.03] transition-colors">
      <td className="px-3 py-2 font-mono text-foreground/45">{rank}</td>
      <td className="px-3 py-2">
        <span
          className="font-mono text-foreground/85"
          title={buyer.buyer_address}
        >
          {shortAddr(buyer.buyer_address)}
        </span>
      </td>
      <td className="px-3 py-2">
        <LabelBadge
          label={buyer.label as BuyerLabel | null}
          confidence={conf}
          reason={buyer.reason ?? null}
          buyerAddress={buyer.buyer_address}
          sellerAddress={sellerAddress}
        />
      </td>
      <td className="px-3 py-2 text-right font-mono">{fmtInt(buyer.tx_count)}</td>
      <td className="px-3 py-2 text-right font-mono hidden sm:table-cell">
        {fmtUsd(buyer.volume)}
      </td>
      <td className="px-3 py-2 text-right font-mono hidden md:table-cell text-foreground/60">
        {conf != null ? conf.toFixed(2) : "—"}
      </td>
    </tr>
  );
}

function BuyerTable({
  buyers,
  startRank = 1,
  sellerAddress,
}: {
  buyers: Buyer[];
  startRank?: number;
  sellerAddress?: string;
}) {
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
          {buyers.map((b, i) => (
            <BuyerRow
              key={b.buyer_address}
              buyer={b}
              rank={startRank + i}
              sellerAddress={sellerAddress}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TopBuyersTable({
  buyers,
  sellerAddress,
}: {
  buyers: ServiceDetail["top_buyers"];
  sellerAddress?: string;
}) {
  if (!buyers.length) {
    return (
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-8 text-center text-sm text-foreground/55">
        No buyers recorded yet.
      </div>
    );
  }

  const main = buyers.filter((b) => b.label !== "owner_test");
  const owner = buyers.filter((b) => b.label === "owner_test");

  return (
    <div className="flex flex-col gap-4">
      {main.length > 0 ? (
        <BuyerTable buyers={main} sellerAddress={sellerAddress} />
      ) : (
        <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-8 text-center text-sm text-foreground/55">
          No external buyers recorded yet.
        </div>
      )}

      {owner.length > 0 && (
        <details className="group rounded-lg border border-foreground/10 bg-foreground/[0.02]">
          <summary className="cursor-pointer list-none px-4 py-3 text-sm text-foreground/70 hover:text-foreground select-none flex items-center justify-between gap-2">
            <span className="inline-flex items-center gap-2">
              <span className="inline-block size-2 rounded-full bg-yellow-300" aria-hidden />
              Operator self-tests
              <span className="text-foreground/45 font-mono text-xs">
                {owner.length}
              </span>
            </span>
            <span className="text-xs text-foreground/45 group-open:hidden">
              Show
            </span>
            <span className="text-xs text-foreground/45 hidden group-open:inline">
              Hide
            </span>
          </summary>
          <div className="px-4 pb-4 pt-1 flex flex-col gap-2">
            <p className="text-xs text-foreground/55">
              Traffic from the operator&apos;s own wallets. Excluded from the
              real-volume and suspected-wash percentages above.
            </p>
            <BuyerTable
              buyers={owner}
              startRank={main.length + 1}
              sellerAddress={sellerAddress}
            />
          </div>
        </details>
      )}
    </div>
  );
}
