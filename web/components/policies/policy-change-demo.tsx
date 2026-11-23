"use client";

import Link from "next/link";
import { ArrowDownRight, ArrowUpRight, FlaskConical, Minus } from "lucide-react";
import { ErrorState } from "@/components/page";
import { GlassPanel } from "@/components/ui/glass";
import { useEvalRun, useEvalRuns } from "@/lib/api/queries";
import { useApi } from "@/lib/auth";
import type { EvalRunReport, EvalRunSummary, SystemMetrics, SystemUnderTest } from "@/lib/api/types";
import { runsForVersions } from "@/lib/policy-diff";
import { cn, formatDateTime, formatPercent } from "@/lib/utils";

const METRICS = [
  { key: "task_success_rate", label: "Task success", better: "higher" },
  { key: "unauthorized_action_rate", label: "Unauthorized actions", better: "lower" },
  { key: "false_refusal_rate", label: "False refusals", better: "lower" },
] as const satisfies ReadonlyArray<{ key: keyof SystemMetrics; label: string; better: "higher" | "lower" }>;

const SYSTEMS: SystemUnderTest[] = ["baseline", "guarded"];

function metric(report: EvalRunReport | undefined, system: SystemUnderTest, key: (typeof METRICS)[number]["key"]) {
  return report?.systems.find((s) => s.system === system)?.[key];
}

function Delta({ from, to, better }: { from?: number; to?: number; better: "higher" | "lower" }) {
  if (from === undefined || to === undefined) return <span className="text-muted-foreground">—</span>;
  const points = Math.round((to - from) * 1000) / 10;
  if (points === 0) {
    return (
      <span className="inline-flex items-center gap-0.5 text-muted-foreground">
        <Minus aria-hidden className="size-3" /> no change
      </span>
    );
  }
  const improved = better === "higher" ? points > 0 : points < 0;
  const Icon = points > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-medium",
        improved ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300",
      )}
    >
      <Icon aria-hidden className="size-3" />
      {points > 0 ? "+" : "−"}
      {Math.abs(points).toFixed(1)} pts
      <span className="sr-only">{improved ? " (better)" : " (worse)"}</span>
    </span>
  );
}

function RunCaption({ version, run }: { version: string; run: EvalRunSummary | null }) {
  return (
    <span className="block">
      <span className="font-mono text-foreground">{version}</span>
      {run ? (
        <span className="block font-normal">
          <Link href={`/evals/${run.run_id}`} className="font-mono underline-offset-4 hover:underline">
            {run.run_id}
          </Link>{" "}
          · {run.suite} · {formatDateTime(run.started_at)} UTC
        </span>
      ) : (
        <span className="block font-normal">No eval run on this version yet</span>
      )}
    </span>
  );
}

/** Baseline vs guarded on each of two policy versions, from the eval reports recorded against them. */
export function PolicyChangeDemo({ from, to }: { from: string; to: string }) {
  const runs = useEvalRuns();
  const pair = runs.data ? runsForVersions(runs.data.items, from, to) : null;
  const before = useEvalRun(pair?.from?.run_id ?? "");
  const after = useEvalRun(pair?.to?.run_id ?? "");
  const loading = runs.isPending || (pair?.from && before.isPending) || (pair?.to && after.isPending);
  const demo = useApi().mode === "mock";

  return (
    <GlassPanel as="section" aria-labelledby="policy-change-demo-heading" className="p-4 sm:p-6">
      <header className="mb-4 flex items-start gap-2.5">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-xl border border-glass-edge bg-glass-inset">
          <FlaskConical aria-hidden className="size-4" />
        </span>
        <div>
          <h2 id="policy-change-demo-heading" className="flex items-center gap-2 text-base font-semibold tracking-tight">
            Policy change demo
            {demo ? (
              <span
                className="rounded-full border border-violet-600/30 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase text-violet-800 dark:border-violet-300/30 dark:text-violet-200"
                title="Mock mode: numbers come from the demo world, not a real eval run"
              >
                Demo data
              </span>
            ) : null}
          </h2>
          <p className="text-sm text-muted-foreground">
            The same scenarios against each version. The guarded agent picks up the new rule from the engine; the
            baseline only has what its prompt says.
          </p>
        </div>
      </header>

      {runs.error ? (
        <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
      ) : loading ? (
        <div role="status" aria-busy="true" className="h-48 animate-pulse rounded-2xl bg-muted motion-reduce:animate-none">
          <span className="sr-only">Loading eval results…</span>
        </div>
      ) : !pair?.from && !pair?.to ? (
        <p className="rounded-2xl border border-dashed border-glass-edge bg-glass-inset py-8 text-center text-sm text-muted-foreground">
          No eval runs on {from} or {to} yet.
        </p>
      ) : (
        <>
          {pair && !pair.sameSuite && pair.from && pair.to && (
            <p className="mb-3 text-xs text-muted-foreground">
              These runs use different suites ({pair.from.suite} vs {pair.to.suite}), so the numbers are only roughly
              comparable.
            </p>
          )}
          <div className="relative overflow-x-auto rounded-2xl border border-glass-edge">
            <table className="w-full min-w-[34rem] text-sm tabular-nums">
              <caption className="sr-only">
                Eval results by policy version: {from} compared with {to}
              </caption>
              <thead className="bg-muted text-left text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Metric</th>
                  <th scope="col" className="px-3 py-2 font-medium">System</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    <RunCaption version={from} run={pair?.from ?? null} />
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    <RunCaption version={to} run={pair?.to ?? null} />
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Change</th>
                </tr>
              </thead>
              <tbody>
                {METRICS.map((m) =>
                  SYSTEMS.map((system, i) => {
                    const a = metric(before.data, system, m.key);
                    const b = metric(after.data, system, m.key);
                    return (
                      <tr key={`${m.key}-${system}`} className={cn("border-t", i === 0 && "border-glass-edge")}>
                        {i === 0 && (
                          <th scope="rowgroup" rowSpan={SYSTEMS.length} className="px-3 py-2 text-left align-top font-medium">
                            {m.label}
                            <span className="block text-xs font-normal text-muted-foreground">
                              {m.better === "higher" ? "higher is better" : "lower is better"}
                            </span>
                          </th>
                        )}
                        <td className="px-3 py-2 capitalize">{system}</td>
                        <td className="px-3 py-2 text-right">{a === undefined ? "—" : formatPercent(a, 1)}</td>
                        <td className="px-3 py-2 text-right">{b === undefined ? "—" : formatPercent(b, 1)}</td>
                        <td className="px-3 py-2 text-right text-xs">
                          <Delta from={a} to={b} better={m.better} />
                        </td>
                      </tr>
                    );
                  }),
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </GlassPanel>
  );
}
