"use client";

import {
  CartesianGrid,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useTheme } from "next-themes";
import { GlassPanel } from "@/components/ui/glass";
import type { SystemMetrics } from "@/lib/api/types";
import { passHatKRows } from "@/lib/pass-hat-k";
import { formatPercent } from "@/lib/utils";

const PALETTE = {
  light: { baseline: "#6e6e73", guarded: "#047857", tick: "#5f5f66", grid: "rgba(15,15,20,0.1)" },
  dark: { baseline: "#a1a1a6", guarded: "#34d399", tick: "#a1a1a6", grid: "rgba(255,255,255,0.1)" },
};

export { passHatKRows };

const pct = (v: unknown) => (typeof v === "number" ? formatPercent(v) : "");

export function PassHatKChart({ baseline, guarded }: { baseline: SystemMetrics; guarded: SystemMetrics }) {
  const rows = passHatKRows(baseline, guarded);
  const summary = rows
    .map((r) => `k=${r.k}: baseline ${pct(r.baseline)}, guarded ${pct(r.guarded)}`)
    .join("; ");
  const COLORS = PALETTE[useTheme().resolvedTheme === "light" ? "light" : "dark"];
  const tick = { fontSize: 12, fill: COLORS.tick };

  return (
    <GlassPanel as="figure" className="p-5">
      <figcaption className="mb-1">
        <h3 className="text-sm font-medium">pass^k — reliability across repeated trials</h3>
        <p className="text-xs text-muted-foreground">
          Probability that all k trials of a scenario succeed. Higher is better; a flat line means consistent behavior.
        </p>
      </figcaption>
      <div role="img" aria-label={`pass^k line chart. ${summary}`} className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 20, right: 24, bottom: 20, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
            <XAxis
              dataKey="k"
              tick={tick}
              stroke={COLORS.grid}
              label={{ value: "k (trials that must all pass)", position: "insideBottom", offset: -12, fontSize: 12, fill: COLORS.tick }}
            />
            <YAxis domain={[0, 1]} tickFormatter={pct} tick={tick} stroke={COLORS.grid} width={48} />
            <Tooltip
              formatter={(v) => pct(v)}
              labelFormatter={(k) => `k = ${k}`}
              contentStyle={{
                background: "var(--popover)",
                border: "1px solid var(--glass-border)",
                borderRadius: 14,
                color: "var(--popover-foreground)",
                backdropFilter: "blur(24px)",
              }}
            />
            <Legend verticalAlign="top" height={28} wrapperStyle={{ color: COLORS.tick, fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="baseline"
              name="Baseline (dashed, squares)"
              stroke={COLORS.baseline}
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 4, strokeWidth: 2, fill: COLORS.baseline }}
              legendType="square"
              isAnimationActive={false}
            >
              <LabelList dataKey="baseline" position="bottom" formatter={pct} fontSize={11} fill={COLORS.tick} />
            </Line>
            <Line
              type="monotone"
              dataKey="guarded"
              name="Guarded (solid, circles)"
              stroke={COLORS.guarded}
              strokeWidth={2.5}
              dot={{ r: 4, strokeWidth: 2, fill: COLORS.guarded }}
              legendType="circle"
              isAnimationActive={false}
            >
              <LabelList dataKey="guarded" position="top" formatter={pct} fontSize={11} fill={COLORS.guarded} />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>
      <table className="mt-3 w-full text-xs tabular-nums">
        <caption className="sr-only">pass^k values</caption>
        <thead className="text-muted-foreground">
          <tr>
            <th scope="col" className="py-1 text-left font-medium">k</th>
            {rows.map((r) => (
              <th key={r.k} scope="col" className="py-1 text-right font-medium">{r.k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-t">
            <th scope="row" className="py-1 text-left font-medium">Baseline</th>
            {rows.map((r) => <td key={r.k} className="py-1 text-right">{pct(r.baseline)}</td>)}
          </tr>
          <tr className="border-t">
            <th scope="row" className="py-1 text-left font-medium">Guarded</th>
            {rows.map((r) => <td key={r.k} className="py-1 text-right font-semibold">{pct(r.guarded)}</td>)}
          </tr>
        </tbody>
      </table>
    </GlassPanel>
  );
}
