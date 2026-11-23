import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { GlassPanel } from "@/components/ui/glass";
import type { SystemMetrics } from "@/lib/api/types";
import { cn, formatPercent } from "@/lib/utils";

export type MetricKey =
  | "task_success_rate"
  | "unauthorized_action_rate"
  | "false_refusal_rate"
  | "correct_escalation_rate"
  | "latency_ms_p95"
  | "cost_usd_per_resolved";

export interface MetricDef {
  key: MetricKey;
  label: string;
  better: "higher" | "lower";
  format: (v: number) => string;
}

export const HEADLINE_METRICS: MetricDef[] = [
  { key: "task_success_rate", label: "Task success", better: "higher", format: (v) => formatPercent(v, 1) },
  { key: "unauthorized_action_rate", label: "Unauthorized action rate", better: "lower", format: (v) => formatPercent(v, 1) },
  { key: "false_refusal_rate", label: "False refusals", better: "lower", format: (v) => formatPercent(v, 1) },
  { key: "correct_escalation_rate", label: "Escalation accuracy", better: "higher", format: (v) => formatPercent(v, 1) },
  { key: "latency_ms_p95", label: "P95 latency", better: "lower", format: (v) => `${(v / 1000).toFixed(2)} s` },
  { key: "cost_usd_per_resolved", label: "Cost per resolved", better: "lower", format: (v) => `$${v.toFixed(4)}` },
];

export function MetricCard({
  def,
  baseline,
  guarded,
}: {
  def: MetricDef;
  baseline: SystemMetrics;
  guarded: SystemMetrics;
}) {
  const b = baseline[def.key];
  const g = guarded[def.key];
  const diff = g - b;
  const improved = def.better === "higher" ? diff > 0 : diff < 0;
  const same = Math.abs(diff) < 1e-9;
  const DeltaIcon = same ? Minus : diff > 0 ? ArrowUp : ArrowDown;
  const emphasis = def.key === "unauthorized_action_rate";

  return (
    <GlassPanel
      as="section"
      aria-label={def.label}
      className={cn("p-5", emphasis && "border-emerald-600/40 dark:border-emerald-300/30")}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-medium">{def.label}</h3>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap uppercase",
            def.better === "lower" ? "border-sky-600/40 text-sky-800 dark:border-sky-300/30 dark:text-sky-200" : "text-muted-foreground",
          )}
        >
          {def.better === "lower" ? "↓ lower is better" : "↑ higher is better"}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-2">
        <div>
          <dt className="text-xs text-muted-foreground">Baseline</dt>
          <dd className="text-lg tabular-nums text-muted-foreground">{def.format(b)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Guarded</dt>
          <dd className="text-3xl font-semibold tracking-tight tabular-nums">{def.format(g)}</dd>
        </div>
      </dl>
      <p
        className={cn(
          "mt-2 flex items-center gap-1 text-xs",
          same ? "text-muted-foreground" : improved ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300",
        )}
      >
        <DeltaIcon aria-hidden className="size-3.5" />
        {same ? "No change" : `${def.format(Math.abs(diff))} ${improved ? "better" : "worse"} than baseline`}
      </p>
    </GlassPanel>
  );
}
