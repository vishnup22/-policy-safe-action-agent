"use client";

import { Fragment, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ChevronDown, CircleCheck, CircleX } from "lucide-react";
import { HEADLINE_METRICS, MetricCard } from "@/components/evals/metric-card";
import { PassHatKChart } from "@/components/evals/pass-hat-k-chart";
import { ErrorState, LoadingState, PageHeader } from "@/components/page";
import { buttonVariants } from "@/components/ui/button";
import type { ScenarioCategory, ScenarioResult, TrialResult } from "@/lib/api/types";
import { useEvalRun } from "@/lib/api/queries";
import { cn, formatDateTime, formatPercent } from "@/lib/utils";

function categoryLabel(c: string) {
  return c.replace(/_/g, " ");
}

function passCount(r: ScenarioResult | undefined) {
  if (!r) return "—";
  return `${r.trials.filter((t) => t.success).length}/${r.trials.length}`;
}

function TrialTable({ system, trials }: { system: string; trials: TrialResult[] }) {
  return (
    <div className="min-w-0">
      <h4 className="mb-1 text-xs font-semibold capitalize">{system}</h4>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-xs tabular-nums">
          <thead className="bg-muted/50 text-left text-muted-foreground">
            <tr>
              <th scope="col" className="px-2 py-1.5 font-medium">Trial</th>
              <th scope="col" className="px-2 py-1.5 font-medium">Result</th>
              <th scope="col" className="px-2 py-1.5 font-medium">Unauthorized</th>
              <th scope="col" className="px-2 py-1.5 text-right font-medium">Turns</th>
              <th scope="col" className="px-2 py-1.5 text-right font-medium">P95</th>
              <th scope="col" className="px-2 py-1.5 text-right font-medium">Cost</th>
              <th scope="col" className="px-2 py-1.5 font-medium">Note</th>
            </tr>
          </thead>
          <tbody>
            {trials.map((t) => (
              <tr key={t.trial} className="border-t">
                <td className="px-2 py-1.5">{t.trial + 1}</td>
                <td className="px-2 py-1.5">
                  {t.success ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                      <CircleCheck aria-hidden className="size-3.5" /> pass
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-red-700 dark:text-red-400">
                      <CircleX aria-hidden className="size-3.5" /> fail
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5 font-mono">
                  {t.unauthorized_actions.length ? t.unauthorized_actions.join(", ") : "—"}
                </td>
                <td className="px-2 py-1.5 text-right">{t.turns}</td>
                <td className="px-2 py-1.5 text-right">{(t.latency_ms_p95 / 1000).toFixed(1)} s</td>
                <td className="px-2 py-1.5 text-right">${t.cost_usd.toFixed(4)}</td>
                <td className="px-2 py-1.5">
                  {t.false_refusal ? "False refusal" : t.failure_reason ?? (t.escalated ? "Escalated" : "")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function EvalRunDetail({ runId }: { runId: string }) {
  const { data, error, isPending, refetch } = useEvalRun(runId);
  const [open, setOpen] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<ScenarioCategory | "all">("all");

  const scenarioRows = useMemo(() => {
    if (!data) return [];
    const ids = [...new Set(data.scenarios.map((s) => s.scenario_id))];
    return ids.map((id) => {
      const baseline = data.scenarios.find((s) => s.scenario_id === id && s.system === "baseline");
      const guarded = data.scenarios.find((s) => s.scenario_id === id && s.system === "guarded");
      return { id, category: (baseline ?? guarded)!.category, baseline, guarded };
    });
  }, [data]);

  const back = (
    <Link href="/evals" className={buttonVariants({ variant: "ghost", size: "sm" })}>
      <ArrowLeft aria-hidden /> All runs
    </Link>
  );

  if (isPending) return <LoadingState label="Loading eval report…" />;
  if (error) return (<>{back}<ErrorState error={error} onRetry={() => void refetch()} /></>);

  const baseline = data.systems.find((s) => s.system === "baseline");
  const guarded = data.systems.find((s) => s.system === "guarded");
  if (!baseline || !guarded) {
    return (<>{back}<ErrorState error={new Error("This report is missing a baseline or guarded system.")} /></>);
  }

  const categories = [
    ...new Set([...Object.keys(baseline.by_category), ...Object.keys(guarded.by_category)]),
  ] as ScenarioCategory[];
  const filteredRows =
    categoryFilter === "all" ? scenarioRows : scenarioRows.filter((r) => r.category === categoryFilter);

  return (
    <>
      <div className="mb-2">{back}</div>
      <PageHeader
        title={<span className="font-mono">{data.run_id}</span>}
        description={
          <>
            <span className="rounded border px-1 text-xs font-medium uppercase">{data.suite}</span> ·{" "}
            {formatDateTime(data.started_at)}–{formatDateTime(data.finished_at)} UTC · {guarded.scenarios} scenarios ×{" "}
            {guarded.trials_per_scenario} trials · sha <span className="font-mono">{data.git_sha}</span> · policy{" "}
            <span className="font-mono">{data.policy_version}</span> · agent <span className="font-mono">{data.agent_model}</span>
          </>
        }
      />

      <section aria-label="Headline metrics" className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {HEADLINE_METRICS.map((def) => (
          <MetricCard key={def.key} def={def} baseline={baseline} guarded={guarded} />
        ))}
      </section>

      <div className="mb-5 grid gap-4 lg:grid-cols-2">
        <PassHatKChart baseline={baseline} guarded={guarded} />

        <section className="rounded-xl border bg-card p-4" aria-labelledby="cat-heading">
          <h3 id="cat-heading" className="text-sm font-medium">Success by category</h3>
          <p className="mb-2 text-xs text-muted-foreground">
            Injection resistance: baseline {formatPercent(baseline.injection_resistance_rate)} → guarded{" "}
            {formatPercent(guarded.injection_resistance_rate)} · duplicate side effects: baseline{" "}
            {baseline.duplicate_side_effects} → guarded {guarded.duplicate_side_effects}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs tabular-nums">
              <thead className="text-left text-muted-foreground">
                <tr>
                  <th scope="col" className="py-1.5 font-medium">Category</th>
                  <th scope="col" className="py-1.5 text-right font-medium">Baseline</th>
                  <th scope="col" className="py-1.5 text-right font-medium">Guarded</th>
                  <th scope="col" className="py-1.5 text-right font-medium">Δ</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((c) => {
                  const b = baseline.by_category[c] ?? 0;
                  const g = guarded.by_category[c] ?? 0;
                  const d = g - b;
                  return (
                    <tr key={c} className="border-t">
                      <th scope="row" className="py-1.5 text-left font-normal capitalize">{categoryLabel(c)}</th>
                      <td className="py-1.5 text-right text-muted-foreground">{formatPercent(b)}</td>
                      <td className="py-1.5 text-right font-semibold">{formatPercent(g)}</td>
                      <td className={cn("py-1.5 text-right", d > 0 ? "text-emerald-700 dark:text-emerald-400" : d < 0 ? "text-red-700 dark:text-red-400" : "")}>
                        {d > 0 ? "+" : d < 0 ? "−" : "±"}
                        {formatPercent(Math.abs(d))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <section aria-labelledby="scenarios-heading" className="rounded-xl border bg-card">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
          <h3 id="scenarios-heading" className="text-sm font-medium">Scenarios</h3>
          <label className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Category</span>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value as ScenarioCategory | "all")}
              className="rounded-md border bg-background px-2 py-1 capitalize"
            >
              <option value="all">All</option>
              {categories.map((c) => (
                <option key={c} value={c}>{categoryLabel(c)}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">Scenario</th>
                <th scope="col" className="hidden px-4 py-2 font-medium sm:table-cell">Category</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">Baseline</th>
                <th scope="col" className="px-4 py-2 text-right font-medium">Guarded</th>
                <th scope="col" className="w-8"><span className="sr-only">Expand</span></th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((r) => {
                const expanded = open === r.id;
                return (
                  <Fragment key={r.id}>
                    <tr className="border-t">
                      <td className="px-4 py-2">
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-controls={`trials-${r.id}`}
                          onClick={() => setOpen(expanded ? null : r.id)}
                          className="font-mono text-xs underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                        >
                          {r.id}
                        </button>
                      </td>
                      <td className="hidden px-4 py-2 text-xs capitalize text-muted-foreground sm:table-cell">{categoryLabel(r.category)}</td>
                      <td className="px-4 py-2 text-right text-xs tabular-nums">{passCount(r.baseline)}</td>
                      <td className="px-4 py-2 text-right text-xs font-semibold tabular-nums">{passCount(r.guarded)}</td>
                      <td className="pr-3">
                        <ChevronDown aria-hidden className={cn("size-4 text-muted-foreground transition-transform", expanded && "rotate-180")} />
                      </td>
                    </tr>
                    {expanded && (
                      <tr id={`trials-${r.id}`} className="bg-muted/20">
                        <td colSpan={5} className="px-4 py-3">
                          <div className="grid gap-3 xl:grid-cols-2">
                            {r.baseline && <TrialTable system="baseline" trials={r.baseline.trials} />}
                            {r.guarded && <TrialTable system="guarded" trials={r.guarded.trials} />}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
