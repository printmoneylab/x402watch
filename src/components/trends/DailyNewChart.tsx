"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { DailyNewServicesPoint } from "@/lib/trends";

const TOOLTIP_STYLE = {
  background: "#0f1116",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 8,
  color: "#e7e9ee",
} as const;

export function DailyNewChart({ data }: { data: DailyNewServicesPoint[] }) {
  return (
    <div className="rounded-lg border border-foreground/10 bg-foreground/[0.02] p-6">
      <h3 className="text-base font-semibold tracking-tight">
        New services per day
      </h3>
      <p className="text-xs text-foreground/55 mb-4">
        Indexed at first_seen, last 14 days.
      </p>
      <div className="h-56">
        {data.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-foreground/40">
            (no data)
          </div>
        ) : (
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
                allowDecimals={false}
                width={36}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" fill="#5eead4" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
