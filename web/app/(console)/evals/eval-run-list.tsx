"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page";
import { useEvalRuns } from "@/lib/api/queries";
import { formatDateTime, formatPercent } from "@/lib/utils";

export function EvalRunList() {
  const { data, error, isPending, refetch } = useEvalRuns();
  return (
    <>
      <PageHeader
        title="Eval runs"
        description="Baseline agent (policy in prompt) vs guarded agent (policy engine decides), on the same scenarios."
      />
      {isPending ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : data.items.length === 0 ? (
        <EmptyState>No eval runs yet.</EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.items.map((r) => (
            <li key={r.run_id}>
              <Link
                href={`/evals/${r.run_id}`}
                className="block rounded-xl border bg-card p-4 transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-ring"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-mono text-sm font-medium">{r.run_id}</p>
                    <p className="text-xs text-muted-foreground">
                      <span className="rounded border px-1 font-medium uppercase">{r.suite}</span> ·{" "}
                      {formatDateTime(r.started_at)} UTC · <span className="font-mono">{r.git_sha}</span> · policy{" "}
                      <span className="font-mono">{r.policy_version}</span>
                    </p>
                  </div>
                  <ChevronRight aria-hidden className="size-4 text-muted-foreground" />
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">Task success ↑</dt>
                    <dd className="tabular-nums">
                      <span className="text-muted-foreground">baseline {formatPercent(r.headline.baseline.task_success_rate)}</span>
                      {" → "}
                      <span className="font-semibold">guarded {formatPercent(r.headline.guarded.task_success_rate)}</span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">Unauthorized actions ↓ lower is better</dt>
                    <dd className="tabular-nums">
                      <span className="text-muted-foreground">baseline {formatPercent(r.headline.baseline.unauthorized_action_rate, 1)}</span>
                      {" → "}
                      <span className="font-semibold">guarded {formatPercent(r.headline.guarded.unauthorized_action_rate, 1)}</span>
                    </dd>
                  </div>
                </dl>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
