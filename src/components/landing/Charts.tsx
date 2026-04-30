"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  BarChart,
  Bar,
} from "recharts";
import type {
  LabelDistribution,
  CategoryVolumeSeries,
  DailyNewServices,
} from "@/lib/stats";

const LABEL_COLORS: Record<string, string> = {
  organic_user: "#3ee0a3",
  ai_agent: "#5eead4",
  exchange_user: "#22d3ee",
  self_test: "#f5b400",
  developer: "#a78bfa",
  analytics_bot: "#7dd3fc",
  verifier: "#94a3b8",
  suspected_wash: "#ef4d4d",
};

const SERIES_COLORS = ["#3ee0a3", "#5eead4", "#a78bfa", "#f5b400", "#ef4d4d"];

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
      <div className="h-72">{children}</div>
    </div>
  );
}

export function LabelDonut({ data }: { data: LabelDistribution }) {
  return (
    <ChartShell
      title="Buyer label distribution"
      caption="8-label classification per buyer (latest)."
    >
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="n_buyers"
            nameKey="label"
            innerRadius={55}
            outerRadius={95}
            paddingAngle={2}
            stroke="#07080a"
            strokeWidth={2}
          >
            {data.map((d) => (
              <Cell key={d.label} fill={LABEL_COLORS[d.label] ?? "#64748b"} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: "#0f1116",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: "#e7e9ee",
            }}
            formatter={(v, _n, p) =>
              [`${Number(v).toLocaleString()} buyers`, (p as { payload?: { label?: string } } | undefined)?.payload?.label ?? ""]
            }
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

export function CategoryVolumeLine({ data }: { data: CategoryVolumeSeries }) {
  // Pivot: { date, [cat]: total_volume_24h }
  const pivot: Record<string, Record<string, number | string>> = {};
  data.forEach((cat) => {
    cat.points.forEach((p) => {
      if (!pivot[p.date]) pivot[p.date] = { date: p.date };
      pivot[p.date][cat.category] = p.total_volume_24h;
    });
  });
  const rows = Object.values(pivot).sort((a, b) =>
    String(a.date).localeCompare(String(b.date))
  );

  return (
    <ChartShell
      title="Category volume — 30d"
      caption="Top 5 categories by 24h USDC volume, daily."
    >
      <ResponsiveContainer>
        <LineChart data={rows} margin={{ top: 6, right: 8, left: 0, bottom: 6 }}>
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
            contentStyle={{
              background: "#0f1116",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: "#e7e9ee",
            }}
            formatter={(v) => `$${Number(v).toFixed(2)}`}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#9aa1ac" }} />
          {data.map((cat, i) => (
            <Line
              key={cat.category}
              type="monotone"
              dataKey={cat.category}
              stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
              strokeWidth={1.75}
              dot={false}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

export function DailyNewServicesBar({ data }: { data: DailyNewServices }) {
  return (
    <ChartShell
      title="New services per day — 30d"
      caption="Newly indexed services from the Coinbase Bazaar discovery feed."
    >
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 6 }}>
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
            width={48}
          />
          <Tooltip
            contentStyle={{
              background: "#0f1116",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
              color: "#e7e9ee",
            }}
          />
          <Bar dataKey="count" fill="#3ee0a3" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

export function ChartGrid({
  labels,
  series,
  daily,
}: {
  labels: LabelDistribution;
  series: CategoryVolumeSeries;
  daily: DailyNewServices;
}) {
  return (
    <section id="data" className="border-b border-foreground/5 scroll-mt-16">
      <div className="mx-auto max-w-6xl px-6 py-24 sm:py-32">
        <h2 className="text-2xl sm:text-3xl font-semibold tracking-tight mb-3">
          What the data shows.
        </h2>
        <p className="text-sm text-foreground/55 mb-12 max-w-2xl text-pretty">
          Every chart below is rebuilt from the live indexer state, refreshed every 60
          seconds. Hover for exact values.
        </p>
        <div className="grid gap-5 lg:grid-cols-2">
          <div>
            <LabelDonut data={labels} />
          </div>
          <div>
            <DailyNewServicesBar data={daily} />
          </div>
          <div className="lg:col-span-2">
            <CategoryVolumeLine data={series} />
          </div>
        </div>
      </div>
    </section>
  );
}
