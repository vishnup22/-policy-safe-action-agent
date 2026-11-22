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
import type { SystemMetrics } from "@/lib/api/types";
import { formatPercent } from "@/lib/utils";

const COLORS = { baseline: "#78716c", guarded: "#059669" };

export function passHatKRows(baseline: SystemMetrics, guarded: SystemMetrics) {
  const ks = [...new Set([...Object.keys(baseline.pass_hat_k), ...Object.keys(guarded.pass_hat_k)])]
    .map(Number)
    .sort((a, b) => a - b);
  return ks.map((k) => ({
    k: String(k),
    baseline: baseline.pass_hat_k[String(k)] ?? null,
    guarded: guarded.pass_hat_k[String(k)] ?? null,
  }));
}

const pct = (v: unknown) => (typeof v === "number" ? formatPercent(v) : "");

export function PassHatKChart({ baseline, guarded }: { baseline: SystemMetrics; guarded: SystemMetrics }) {
  const rows = passHatKRows(baseline, guarded);
  const summary = rows
    .map((r) => `k=${r.k}: baseline ${pct(r.baseline)}, guarded ${pct(r.guarded)}`)
    .join("; ");

  return (
    <figure className="rounded-xl border bg-card p-4">
      <figcaption className="mb-1">
        <h3 className="text-sm font-medium">pass^k — reliability across repeated trials</h3>
        <p className="text-xs text-muted-foreground">
          Probability that all k trials of a scenario succeed. Higher is better; a flat line means consistent behavior.
        </p>
      </figcaption>
      <div role="img" aria-label={`pass^k line chart. ${summary}`} className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 20, right: 24, bottom: 20, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey="k"
              tick={{ fontSize: 12 }}
              label={{ value: "k (trials that must all pass)", position: "insideBottom", offset: -12, fontSize: 12 }}
            />
            <YAxis domain={[0, 1]} tickFormatter={pct} tick={{ fontSize: 12 }} width={48} />
            <Tooltip formatter={(v) => pct(v)} labelFormatter={(k) => `k = ${k}`} />
            <Legend verticalAlign="top" height={28} />
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
              <LabelList dataKey="baseline" position="bottom" formatter={pct} fontSize={11} />
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
              <LabelList dataKey="guarded" position="top" formatter={pct} fontSize={11} />
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
    </figure>
  );
}
