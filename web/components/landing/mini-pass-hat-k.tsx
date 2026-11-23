import type { SystemMetrics } from "@/lib/api/types";
import { passHatKRows } from "@/lib/pass-hat-k";
import { formatPercent } from "@/lib/utils";

const W = 360;
const H = 170;
const PAD = { l: 40, r: 16, t: 18, b: 28 };

/** Dependency-free pass^k chart for the landing page (recharts stays in the console bundle). */
export function MiniPassHatK({ baseline, guarded }: { baseline: SystemMetrics; guarded: SystemMetrics }) {
  const rows = passHatKRows(baseline, guarded);
  const n = rows.length;
  const x = (i: number) => PAD.l + (n <= 1 ? 0 : (i * (W - PAD.l - PAD.r)) / (n - 1));
  const y = (v: number) => PAD.t + (1 - v) * (H - PAD.t - PAD.b);
  const line = (key: "baseline" | "guarded") =>
    rows.flatMap((r, i) => (r[key] === null ? [] : [`${x(i)},${y(r[key])}`])).join(" ");
  const summary = rows
    .map((r) => `k=${r.k}: baseline ${r.baseline === null ? "n/a" : formatPercent(r.baseline)}, guarded ${r.guarded === null ? "n/a" : formatPercent(r.guarded)}`)
    .join("; ");

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`pass^k by k. ${summary}`} className="h-auto w-full overflow-visible">
      {[0, 0.5, 1].map((v) => (
        <g key={v}>
          <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} style={{ stroke: "var(--border)" }} strokeDasharray="3 4" />
          <text x={PAD.l - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-muted-foreground text-[10px] tabular-nums">
            {formatPercent(v)}
          </text>
        </g>
      ))}
      {rows.map((r, i) => (
        <text key={r.k} x={x(i)} y={H - 6} textAnchor="middle" className="fill-muted-foreground text-[10px]">
          k={r.k}
        </text>
      ))}
      <polyline points={line("baseline")} fill="none" strokeWidth={2} strokeDasharray="6 5" style={{ stroke: "var(--chart-2)" }} />
      <polyline points={line("guarded")} fill="none" strokeWidth={2.5} strokeLinecap="round" style={{ stroke: "var(--chart-1)" }} />
      {rows.map((r, i) => (
        <g key={r.k}>
          {r.baseline !== null && (
            <rect x={x(i) - 3.5} y={y(r.baseline) - 3.5} width={7} height={7} style={{ fill: "var(--chart-2)" }} />
          )}
          {r.guarded !== null && (
            <>
              <circle cx={x(i)} cy={y(r.guarded)} r={4} style={{ fill: "var(--chart-1)" }} />
              <text x={x(i)} y={y(r.guarded) - 9} textAnchor="middle" className="fill-foreground text-[10px] font-semibold tabular-nums">
                {formatPercent(r.guarded)}
              </text>
            </>
          )}
        </g>
      ))}
    </svg>
  );
}
