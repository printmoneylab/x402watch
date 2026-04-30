import { LABEL_COLOR_TW, type LabelDistribution } from "@/lib/categories";
import { cn } from "@/lib/utils";

const ORDER = [
  "organic_user",
  "ai_agent",
  "exchange_user",
  "developer",
  "analytics_bot",
  "self_test",
  "suspected_wash",
  "verifier",
  "unlabeled",
];

export function LabelMiniBar({
  distribution,
  className,
}: {
  distribution: LabelDistribution;
  className?: string;
}) {
  const total = Object.values(distribution).reduce((a, b) => a + b, 0);
  if (total === 0) {
    return (
      <div className={cn("h-1.5 w-full rounded-full bg-foreground/10", className)} />
    );
  }
  const segments = ORDER.filter((l) => (distribution[l] ?? 0) > 0).map((l) => ({
    label: l,
    pct: (distribution[l] / total) * 100,
  }));
  return (
    <div
      className={cn("flex h-1.5 w-full overflow-hidden rounded-full bg-foreground/5", className)}
      role="img"
      aria-label="Buyer label distribution"
    >
      {segments.map((s) => (
        <div
          key={s.label}
          className={LABEL_COLOR_TW[s.label] ?? "bg-zinc-700"}
          style={{ width: `${s.pct}%` }}
          title={`${s.label}: ${s.pct.toFixed(1)}%`}
        />
      ))}
    </div>
  );
}
