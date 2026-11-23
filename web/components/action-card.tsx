"use client";

import { useState } from "react";
import { ChevronDown, CircleCheckBig, Clock, ShieldCheck } from "lucide-react";
import { decidingRules } from "@/lib/decisions";
import { ACTION_LABELS, describeArgs, type ActionView } from "@/lib/events";
import { cn } from "@/lib/utils";
import { DecisionBadge } from "./decision-badge";
import { FactsSnapshot } from "./facts-snapshot";
import { RuleResultsTable } from "./rule-results-table";

function ArgsList({ args }: { args: Record<string, unknown> }) {
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 font-mono text-xs">
      {Object.entries(args)
        .filter(([k]) => k !== "action")
        .map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="break-words">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
          </div>
        ))}
    </dl>
  );
}

function StatusLine({ view }: { view: ActionView }) {
  if (view.executed) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-emerald-700 dark:text-emerald-300">
        <CircleCheckBig aria-hidden className="size-3.5" />
        Executed · <span className="font-mono">{view.executed.payload.idempotency_key}</span>
      </p>
    );
  }
  if (view.failed) {
    return <p className="text-xs text-red-700 dark:text-red-400">Execution failed: {view.failed.payload.error}</p>;
  }
  if (view.approvalId && !view.approvalResolution) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-amber-800 dark:text-amber-300">
        <Clock aria-hidden className="size-3.5" />
        Awaiting human approval · <span className="font-mono">{view.approvalId}</span>
      </p>
    );
  }
  if (view.approvalResolution === "rejected") {
    return <p className="text-xs text-red-700 dark:text-red-400">Approval rejected — not executed</p>;
  }
  if (view.decision && view.decision.outcome !== "ALLOW") {
    return <p className="text-xs text-muted-foreground">Not executed</p>;
  }
  return null;
}

export function ActionCard({ view, defaultExpanded = false }: { view: ActionView; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const { intent, decision } = view;
  const deciding = decision ? decidingRules(decision) : [];

  return (
    <article
      aria-label={`Proposed action: ${ACTION_LABELS[intent.args.action]}`}
      className="overflow-hidden rounded-2xl border border-glass-edge bg-glass-inset text-card-foreground shadow-[inset_0_1px_0_0_var(--glass-highlight)]"
    >
      <header className="flex flex-wrap items-start justify-between gap-2 border-b px-3.5 py-3">
        <div className="min-w-0">
          <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Proposed action</p>
          <p className="font-medium">
            {ACTION_LABELS[intent.args.action]}{" "}
            <span className="font-normal text-muted-foreground">· {describeArgs(intent.args)}</span>
          </p>
        </div>
        {decision ? (
          <DecisionBadge outcome={decision.outcome} />
        ) : (
          <span className="text-xs text-muted-foreground">Awaiting decision…</span>
        )}
      </header>

      <div className="space-y-3 px-3.5 py-3">
        <ArgsList args={intent.args} />

        {decision && (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">Deciding rules:</span>
              {deciding.map((r) => (
                <code key={r.rule_id} className="rounded-md bg-muted px-1.5 py-0.5 font-mono">{r.rule_id}</code>
              ))}
            </div>
            {deciding.some((r) => r.reason_code) && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-muted-foreground">Reason codes:</span>
                {deciding.flatMap((r) =>
                  r.reason_code ? [<code key={r.rule_id} className="rounded-md border px-1.5 py-0.5 font-mono">{r.reason_code}</code>] : [],
                )}
              </div>
            )}
            <ul className="space-y-1 text-sm" aria-label="Customer-safe messages">
              {deciding.map((r) => (
                <li key={r.rule_id} className="flex gap-2">
                  <span aria-hidden className="text-muted-foreground">›</span>
                  {r.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        <StatusLine view={view} />
      </div>

      {decision && (
        <footer className="border-t">
          <button
            type="button"
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
            className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
          >
            <span className="flex items-center gap-1.5">
              <ShieldCheck aria-hidden className="size-3.5" />
              {decision.policy_set} <span className="font-mono">v{decision.policy_version}</span>
            </span>
            <span className="flex items-center gap-1">
              {expanded ? "Hide" : "Show"} all {decision.rule_results.length} rules
              <ChevronDown aria-hidden className={cn("size-3.5 transition-transform", expanded && "rotate-180")} />
            </span>
          </button>
          {expanded && (
            <div className="space-y-3 px-3.5 pb-3.5">
              <RuleResultsTable decision={decision} />
              <div>
                <p className="mb-1 text-xs font-medium">Facts snapshot (system of record)</p>
                <FactsSnapshot facts={decision.facts_snapshot} />
              </div>
              <p className="text-xs text-muted-foreground">
                Agent justification (not used as a fact): “{intent.justification}”
              </p>
            </div>
          )}
        </footer>
      )}
    </article>
  );
}
