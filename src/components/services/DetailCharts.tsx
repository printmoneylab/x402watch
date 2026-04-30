"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { LABEL_COLOR_HEX } from "@/lib/categories";
import type { ServiceDetail } from "@/lib/services";

const TOOLTIP_STYLE = {
  background: "#0f1116",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  color: "#e7e9ee",
} as const;

function ChartShell({
  title,
  caption,
  children,
}: {
  title: string;
  caption: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6">
      <h3 className="text-base font-semibold tracking-tight">{title}</h3>
      <p className="text-xs text-foreground/55 mb-2">{caption}</p>
      <div className="h-64">{children}</div>
    </div>
  );
}

export function ServiceVolumeSeries({
  data,
}: {
  data: ServiceDetail["time_series_30d"];
}) {
  return (
    <ChartShell
      title="Daily volume — last 30 days"
      caption="USDC volume aggregated per UTC day."
    >
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
            tickFormatter={(v) => `$${Number(v).toLocaleString()}`}
            width={64}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(v) => `$${Number(v).toFixed(4)}`}
          />
          <Line
            type="monotone"
            dataKey="volume"
            stroke="#3ee0a3"
            strokeWidth={1.75}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

export function ServiceLabelDonut({
  data,
}: {
  data: ServiceDetail["label_distribution"];
}) {
  if (data.length === 0) {
    return (
      <ChartShell title="Buyer label distribution" caption="No transactions in the last 30 days.">
        <div className="flex items-center justify-center h-full text-foreground/40 text-sm">
          (empty)
        </div>
      </ChartShell>
    );
  }
  return (
    <ChartShell
      title="Buyer label distribution"
      caption="Share of last-30-day transactions by buyer label."
    >
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="n_tx"
            nameKey="label"
            innerRadius={45}
            outerRadius={80}
            paddingAngle={2}
            stroke="#07080a"
            strokeWidth={2}
          >
            {data.map((d) => (
              <Cell key={d.label} fill={LABEL_COLOR_HEX[d.label] ?? "#64748b"} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(v, _n, p) => {
              const item = (p as { payload?: ServiceDetail["label_distribution"][0] })?.payload;
              return [
                `${Number(v).toLocaleString()} tx (${item?.share_pct ?? 0}%)`,
                item?.label ?? "",
              ];
            }}
          />
          <Legend
            verticalAlign="bottom"
            height={36}
            iconType="circle"
            wrapperStyle={{ fontSize: 11, color: "#9aa1ac" }}
          />
        </PieChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}
