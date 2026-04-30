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
  BarChart,
  Bar,
} from "recharts";
import {
  LABEL_COLOR_HEX,
  type CategoryTimeSeriesPoint,
  type CategoryLabelEntry,
  type CategoryPriceBucket,
} from "@/lib/categories";

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

export function VolumeTimeSeries({ data }: { data: CategoryTimeSeriesPoint[] }) {
  return (
    <ChartShell
      title="24h volume — last 30 days"
      caption="Daily snapshot of the rolling 24-hour USDC volume for this category."
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
            formatter={(v) => `$${Number(v).toFixed(2)}`}
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

export function LabelDonut({ data }: { data: CategoryLabelEntry[] }) {
  return (
    <ChartShell
      title="Buyer label distribution"
      caption="Share of the category's last-30-day transactions by buyer label."
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
              const item = (p as { payload?: CategoryLabelEntry })?.payload;
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

export function PriceHistogram({ data }: { data: CategoryPriceBucket[] }) {
  return (
    <ChartShell
      title="Price distribution"
      caption="Number of services per price bucket."
    >
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 6 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
          <XAxis
            dataKey="bucket"
            tick={{ fill: "#9aa1ac", fontSize: 11 }}
            tickLine={false}
            stroke="rgba(255,255,255,0.1)"
          />
          <YAxis
            tick={{ fill: "#9aa1ac", fontSize: 11 }}
            tickLine={false}
            stroke="rgba(255,255,255,0.1)"
            allowDecimals={false}
            width={48}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Bar dataKey="count" fill="#5eead4" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}
