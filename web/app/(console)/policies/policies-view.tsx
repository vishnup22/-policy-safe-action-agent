"use client";

import Link from "next/link";
import { GitCompareArrows } from "lucide-react";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page";
import { buttonVariants } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass";
import { usePolicies, usePolicy } from "@/lib/api/queries";
import type { PolicySummary } from "@/lib/api/types";
import { policyDiffHref, resolveVersions, versionsOf } from "@/lib/policy-diff";
import { formatDateTime } from "@/lib/utils";

function ActiveBadge() {
  return (
    <span className="rounded-full border border-emerald-600/30 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 uppercase dark:border-emerald-300/30 dark:text-emerald-200">
      Active
    </span>
  );
}

function PolicySetCard({ policySet, summaries }: { policySet: string; summaries: PolicySummary[] }) {
  const detail = usePolicy(policySet);
  const versions = versionsOf(summaries, policySet);
  const compare = versions.length > 1 ? resolveVersions(versions, null, null) : null;
  const active = detail.data?.version;
  const byVersion = new Map(summaries.map((s) => [s.version, s]));

  return (
    <GlassPanel as="section" aria-labelledby={`set-${policySet}`} className="p-4 sm:p-6">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={`set-${policySet}`} className="font-mono text-lg font-semibold break-all">{policySet}</h2>
          <p className="text-sm text-muted-foreground">
            {versions.length} {versions.length === 1 ? "version" : "versions"}
            {active && (
              <>
                {" "}
                · the engine evaluates <span className="font-mono text-foreground">{active}</span>
              </>
            )}
          </p>
        </div>
        {compare && (
          <Link href={policyDiffHref(policySet, compare)} className={buttonVariants({ variant: "glass", size: "sm" })}>
            <GitCompareArrows aria-hidden />
            Compare {compare.from} → {compare.to}
          </Link>
        )}
      </header>

      <div className="relative overflow-x-auto rounded-2xl border border-glass-edge">
        <table className="w-full text-sm">
          <caption className="sr-only">Versions of {policySet}</caption>
          <thead className="bg-muted text-left text-xs text-muted-foreground">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">Version</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Rules</th>
              <th scope="col" className="hidden px-3 py-2 font-medium sm:table-cell">Updated</th>
              <th scope="col" className="px-3 py-2 font-medium"><span className="sr-only">Status</span></th>
            </tr>
          </thead>
          <tbody>
            {[...versions].reverse().map((v) => {
              const s = byVersion.get(v)!;
              return (
                <tr key={v} className="border-t">
                  <td className="px-3 py-2 font-mono">{v}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{s.rule_count}</td>
                  <td className="hidden px-3 py-2 text-muted-foreground sm:table-cell">{formatDateTime(s.updated_at)} UTC</td>
                  <td className="px-3 py-2 text-right">{v === active && <ActiveBadge />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {detail.data && (
        <>
          <h3 className="mt-6 mb-2 text-sm font-semibold">
            Rules in <span className="font-mono">{detail.data.version}</span>
          </h3>
          <ul className="divide-y divide-border rounded-2xl border border-glass-edge bg-glass-inset">
            {detail.data.rules.map((rule) => (
              <li key={rule.id} id={`rule-${rule.id}`} className="grid gap-1 px-3 py-2.5 sm:grid-cols-[16rem_minmax(0,1fr)] sm:gap-4">
                <span className="min-w-0">
                  {compare ? (
                    <Link
                      href={policyDiffHref(policySet, { from: detail.data.version, rule: rule.id })}
                      className="font-mono text-xs font-medium break-all underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      {rule.id}
                    </Link>
                  ) : (
                    <span className="font-mono text-xs font-medium break-all">{rule.id}</span>
                  )}
                </span>
                <span className="min-w-0 text-sm">
                  {rule.description}
                  <span className="mt-1 flex flex-wrap gap-1">
                    {rule.applies_to.map((a) => (
                      <code key={a} className="rounded-md border px-1.5 font-mono text-[11px] text-muted-foreground">
                        {a}
                      </code>
                    ))}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {detail.error && <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />}
    </GlassPanel>
  );
}

export function PoliciesView() {
  const { data, error, isPending, refetch } = usePolicies();
  const sets = data ? [...new Set(data.items.map((p) => p.policy_set))] : [];
  return (
    <>
      <PageHeader
        title="Policies"
        description="Versioned YAML rule sets. The engine evaluates the active version, and every decision records which version decided it."
      />
      {isPending ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : sets.length === 0 ? (
        <EmptyState>No policies loaded.</EmptyState>
      ) : (
        <div className="space-y-6">
          {sets.map((set) => (
            <PolicySetCard key={set} policySet={set} summaries={data.items} />
          ))}
        </div>
      )}
    </>
  );
}
