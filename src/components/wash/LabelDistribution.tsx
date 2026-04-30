"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { LABEL_COLOR_HEX, LABEL_COLOR_TW } from "@/lib/categories";
import {
  WASH_LABELS,
  WASH_LABEL_INFO,
  type WashLabel,
  type WashReportPayload,
} from "@/lib/wash";
import { cn } from "@/lib/utils";

const TOOLTIP_STYLE = {
  background: "#0f1116",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  color: "#e7e9ee",
} as const;

const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);

export function LabelDistribution({
  distribution,
}: {
  distribution: WashReportPayload["label_distribution"];
}) {
  const total = WASH_LABELS.reduce(
    (acc, l) => acc + (distribution[l] ?? 0),
    0
  );

  // Donut data, kept in priority order so colors stay consistent with
  // descriptions below.
  const donutData = WASH_LABELS.map((l) => ({
    label: l,
    n: distribution[l] ?? 0,
  })).filter((d) => d.n > 0);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,320px)_1fr]">
      <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6">
        <h3 className="text-base font-semibold tracking-tight">
          Pattern distribution
        </h3>
        <p className="text-xs text-foreground/55 mb-3">
          Active buyers (30d) by label.
        </p>
        <div className="h-56">
          {donutData.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-foreground/40">
              (no data)
            </div>
          ) : (
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={donutData}
                  dataKey="n"
                  nameKey="label"
                  innerRadius={50}
                  outerRadius={88}
                  paddingAngle={2}
                  stroke="#07080a"
                  strokeWidth={2}
                >
                  {donutData.map((d) => (
                    <Cell
                      key={d.label}
                      fill={LABEL_COLOR_HEX[d.label] ?? "#64748b"}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  formatter={(v, _n, p) => {
                    const item = (p as { payload?: { label: string; n: number } })?.payload;
                    if (!item) return [String(v), ""];
                    const pct = total > 0 ? ((item.n / total) * 100).toFixed(1) : "0.0";
                    return [`${fmtInt(item.n)} buyers (${pct}%)`, item.label];
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <ul className="grid gap-3 sm:grid-cols-2">
        {WASH_LABELS.map((l) => (
          <LabelRow
            key={l}
            label={l}
            count={distribution[l] ?? 0}
            total={total}
          />
        ))}
      </ul>
    </div>
  );
}

function LabelRow({
  label,
  count,
  total,
}: {
  label: WashLabel;
  count: number;
  total: number;
}) {
  const info = WASH_LABEL_INFO[label];
  const pct = total > 0 ? ((count / total) * 100).toFixed(1) : "0.0";
  return (
    <li className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-4">
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className={cn(
            "inline-block size-2 rounded-full",
            LABEL_COLOR_TW[label] ?? "bg-zinc-700"
          )}
          aria-hidden
        />
        <span className="font-mono text-sm text-foreground/90">{label}</span>
        <span className="ml-auto font-mono text-xs text-foreground/55">
          {fmtInt(count)}{" "}
          <span className="text-foreground/35">/ {pct}%</span>
        </span>
      </div>
      <p className="text-xs text-foreground/65 leading-relaxed">
        {info.definition}
      </p>
      <p className="mt-1.5 text-[11px] text-foreground/45 italic leading-relaxed">
        {info.pattern}
      </p>
    </li>
  );
}
