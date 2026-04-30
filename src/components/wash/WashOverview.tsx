"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { WashStats, WashTimeSeriesPoint } from "@/lib/wash";

const fmtInt = (n: number) => new Intl.NumberFormat("en-US").format(n);
const TOOLTIP_STYLE = {
  background: "#0f1116",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  color: "#e7e9ee",
} as const;

export function WashStatsRow({ stats }: { stats: WashStats }) {
  const pct = (n: number, total: number) =>
    total > 0 ? `${((n / total) * 100).toFixed(1)}%` : "—";
  const items = [
    {
      label: "Active buyers (30d)",
      value: fmtInt(stats.total_active_buyers_30d),
      sub: null as string | null,
    },
    {
      label: "Real volume %",
      value: `${stats.real_volume_pct.toFixed(1)}%`,
      sub: "after wash filter",
      accent: "text-emerald-400",
    },
    {
      label: "Suspected wash",
      value: fmtInt(stats.suspected_wash_count),
      sub: pct(stats.suspected_wash_count, stats.total_active_buyers_30d),
      accent: "text-rose-400",
    },
    {
      label: "Self-test detected",
      value: fmtInt(stats.self_test_count),
      sub: pct(stats.self_test_count, stats.total_active_buyers_30d),
      accent: "text-amber-400",
    },
  ];
  return (
    <dl className="grid grid-cols-2 sm:grid-cols-4 gap-y-6 gap-x-6">
      {items.map((it) => (
        <div key={it.label} className="flex flex-col gap-1">
          <dt className="order-2 text-[11px] uppercase tracking-wide text-foreground/55">
            {it.label}
          </dt>
          <dd
            className={`order-1 font-mono text-2xl sm:text-3xl font-medium tracking-tight ${it.accent ?? ""}`}
          >
            {it.value}
          </dd>
          {it.sub && (
            <dd className="order-3 text-xs text-foreground/45">{it.sub}</dd>
          )}
        </div>
      ))}
    </dl>
  );
}

export function WashTimeSeriesChart({ data }: { data: WashTimeSeriesPoint[] }) {
  return (
    <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6">
      <h3 className="text-base font-semibold tracking-tight">
        Wash share — last 14 days
      </h3>
      <p className="text-xs text-foreground/55 mb-4">
        Daily share of transactions classified as suspected_wash and self_test.
      </p>
      <div className="h-56">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-foreground/40">
            (no data)
          </div>
        ) : (
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 6 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: "#9aa1ac", fontSize: 11 }}
                tickLine={false}
                stroke="rgba(255,255,255,0.1)"
                minTickGap={24}
              />
              <YAxis
                tick={{ fill: "#9aa1ac", fontSize: 11 }}
                tickLine={false}
                stroke="rgba(255,255,255,0.1)"
                tickFormatter={(v) => `${v}%`}
                width={40}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(v) => `${Number(v).toFixed(1)}%`}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, color: "#9aa1ac" }}
                iconType="circle"
              />
              <Line
                type="monotone"
                name="suspected_wash"
                dataKey="wash_pct"
                stroke="#f43f5e"
                strokeWidth={1.75}
                dot={false}
                activeDot={{ r: 4 }}
              />
              <Line
                type="monotone"
                name="self_test"
                dataKey="self_test_pct"
                stroke="#fbbf24"
                strokeWidth={1.75}
                dot={false}
                activeDot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
