import type { LandingStats } from "@/lib/stats";

function fmtInt(n: number) {
  return new Intl.NumberFormat("en-US").format(n);
}

function fmtPct(n: number) {
  return `${n.toFixed(1)}%`;
}

const items = (s: LandingStats) =>
  [
    { value: fmtInt(s.services_indexed), label: "services indexed" },
    { value: fmtInt(s.transactions_analyzed), label: "transactions analyzed" },
    { value: fmtInt(s.active_buyers), label: "active buyers labeled" },
    { value: fmtPct(s.real_volume_pct), label: "real volume detected" },
  ] as const;

export function Stats({ stats }: { stats: LandingStats }) {
  return (
    <section className="border-y border-foreground/15 sm:border-y-0 sm:border-b sm:border-foreground/10 bg-foreground/[0.12] sm:bg-foreground/[0.08]">
      <div className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
        <dl className="grid grid-cols-2 gap-y-12 gap-x-6 sm:grid-cols-4">
          {items(stats).map((it) => (
            <div key={it.label} className="flex flex-col gap-1">
              <dt className="order-2 text-xs uppercase tracking-wide text-foreground/55">
                {it.label}
              </dt>
              <dd className="order-1 font-mono text-3xl sm:text-4xl font-medium tracking-tight">
                {it.value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-10 text-xs text-foreground/40">
          Refreshed every 60 seconds · last update {new Date(stats.last_updated).toUTCString()}
        </p>
      </div>
    </section>
  );
}

/** The "differentiator headline" — the single sentence that frames the product. */
export function ProductLine() {
  return (
    <section className="border-b border-foreground/5">
      <div className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
        <p className="text-3xl sm:text-5xl font-medium tracking-tight max-w-[26ch] sm:max-w-[30ch] leading-[1.15] text-balance">
          Most x402 dashboards <span className="text-foreground/50">count transactions.</span>{" "}
          <span className="text-accent">We classify them.</span>
        </p>
      </div>
    </section>
  );
}
