"use client";

import { useEffect, useId, useMemo } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowLeftRight, Info } from "lucide-react";
import { ErrorState, LoadingState, PageHeader } from "@/components/page";
import { PolicyChangeDemo } from "@/components/policies/policy-change-demo";
import { RuleDiffCard } from "@/components/policies/rule-diff";
import { Button } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass";
import { usePolicies, usePolicy, usePolicyDiff } from "@/lib/api/queries";
import type { PolicyDiff } from "@/lib/api/types";
import { policyDiffHref, resolveVersions, versionsOf } from "@/lib/policy-diff";
import { cn } from "@/lib/utils";

const SELECT_CLASS =
  "w-full min-w-0 rounded-full border border-glass-edge bg-glass-inset px-3 py-1.5 font-mono text-sm hover:border-glass-edge-hover focus-visible:outline-2 focus-visible:outline-ring sm:w-auto [&>option]:bg-background";

function VersionPicker({
  label,
  value,
  versions,
  active,
  onChange,
}: {
  label: string;
  value: string;
  versions: string[];
  active?: string;
  onChange: (v: string) => void;
}) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-none">
      <label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
      </label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={SELECT_CLASS}>
        {versions.map((v) => (
          <option key={v} value={v}>
            {v}
            {v === active ? " (active)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}

function Summary({ diff }: { diff: PolicyDiff }) {
  const parts = [
    { n: diff.changed.length, label: "changed" },
    { n: diff.added.length, label: "added" },
    { n: diff.removed.length, label: "removed" },
    { n: diff.unchanged.length, label: "unchanged" },
  ];
  return (
    <p className="text-sm text-muted-foreground" aria-live="polite">
      {parts.map((p, i) => (
        <span key={p.label}>
          {i > 0 && " · "}
          <span className="font-semibold text-foreground tabular-nums">{p.n}</span> {p.label}
        </span>
      ))}
    </p>
  );
}

function DiffBody({ diff, rule }: { diff: PolicyDiff; rule: string | null }) {
  const cards = [
    ...diff.changed.map((c) => ({ id: c.id, kind: "changed" as const, before: c.before, after: c.after })),
    ...diff.added.map((a) => ({ id: a.id, kind: "added" as const, before: undefined, after: a.rule })),
    ...diff.removed.map((r) => ({ id: r.id, kind: "removed" as const, before: r.rule, after: undefined })),
  ];
  const ruleUnchanged = rule !== null && diff.unchanged.includes(rule);
  const ruleUnknown = rule !== null && !ruleUnchanged && !cards.some((c) => c.id === rule);

  return (
    <div className="space-y-4">
      {ruleUnchanged && (
        <p role="note" className="flex items-start gap-2 rounded-2xl border border-glass-edge bg-glass-inset px-4 py-3 text-sm">
          <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span>
            <span className="font-mono font-medium">{rule}</span> is the same in {diff.from_version} and {diff.to_version}.
          </span>
        </p>
      )}
      {ruleUnknown && (
        <p role="note" className="flex items-start gap-2 rounded-2xl border border-glass-edge bg-glass-inset px-4 py-3 text-sm">
          <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span>
            <span className="font-mono font-medium">{rule}</span> isn&apos;t in {diff.from_version} or {diff.to_version}.
          </span>
        </p>
      )}
      {cards.length === 0 ? (
        <p className="rounded-3xl border border-dashed border-glass-edge bg-glass-inset py-10 text-center text-sm text-muted-foreground">
          {diff.from_version === diff.to_version
            ? "Pick two different versions to see what changed."
            : "No rule differs between these versions."}
        </p>
      ) : (
        cards.map((c) => (
          <RuleDiffCard
            key={`${c.kind}-${c.id}`}
            id={c.id}
            kind={c.kind}
            before={c.before}
            after={c.after}
            fromVersion={diff.from_version}
            toVersion={diff.to_version}
            highlighted={c.id === rule}
          />
        ))
      )}
      {diff.unchanged.length > 0 && (
        <GlassPanel as="section" aria-labelledby="unchanged-heading" className="p-4 sm:p-6">
          <details open={ruleUnchanged || undefined}>
            <summary className="cursor-pointer rounded-full text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              <span id="unchanged-heading">Unchanged rules ({diff.unchanged.length})</span>
            </summary>
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {diff.unchanged.map((id) => (
                <li key={id}>
                  <code
                    id={`rule-${id}`}
                    className={cn(
                      "inline-block rounded-md border px-1.5 py-0.5 font-mono text-xs",
                      id === rule ? "border-ring bg-muted font-semibold ring-2 ring-ring" : "text-muted-foreground",
                    )}
                  >
                    {id}
                  </code>
                </li>
              ))}
            </ul>
          </details>
        </GlassPanel>
      )}
    </div>
  );
}

export function PolicyDiffView({ policySet }: { policySet: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const rule = params.get("rule");
  const policies = usePolicies();
  const active = usePolicy(policySet).data?.version;

  const versions = useMemo(() => (policies.data ? versionsOf(policies.data.items, policySet) : []), [policies.data, policySet]);
  const selected = resolveVersions(versions, params.get("from"), params.get("to"));
  const diff = usePolicyDiff(policySet, selected);

  useEffect(() => {
    if (!rule || !diff.data?.unchanged.includes(rule)) return;
    document.getElementById(`rule-${rule}`)?.scrollIntoView?.({ block: "center" });
  }, [rule, diff.data]);

  function go(next: { from: string; to: string }) {
    router.replace(policyDiffHref(policySet, { ...next, rule: rule ?? undefined }), { scroll: false });
  }

  return (
    <>
      <Link
        href="/policies"
        className="mb-3 inline-flex items-center gap-1 self-start rounded-full text-sm text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
      >
        <ArrowLeft aria-hidden className="size-3.5" /> Policies
      </Link>
      <PageHeader
        title="Policy diff"
        description={
          <>
            Rule-level changes in <span className="font-mono text-foreground">{policySet}</span> between two versions.
          </>
        }
      />

      {policies.isPending ? (
        <LoadingState />
      ) : policies.error ? (
        <ErrorState error={policies.error} onRetry={() => void policies.refetch()} />
      ) : !selected ? (
        <ErrorState error={new Error(`No versions of ${policySet} are loaded.`)} />
      ) : (
        <div className="space-y-6">
          <GlassPanel className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end sm:justify-between sm:p-5">
            <div role="group" aria-label="Versions to compare" className="flex min-w-0 items-end gap-2">
              <VersionPicker label="From" value={selected.from} versions={versions} active={active} onChange={(from) => go({ from, to: selected.to })} />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Swap versions"
                className="mb-0.5 shrink-0"
                onClick={() => go({ from: selected.to, to: selected.from })}
              >
                <ArrowLeftRight aria-hidden />
              </Button>
              <VersionPicker label="To" value={selected.to} versions={versions} active={active} onChange={(to) => go({ from: selected.from, to })} />
            </div>
            {diff.data && <Summary diff={diff.data} />}
          </GlassPanel>

          {diff.isPending ? (
            <LoadingState label="Comparing versions…" />
          ) : diff.error ? (
            <ErrorState error={diff.error} onRetry={() => void diff.refetch()} />
          ) : (
            <DiffBody diff={diff.data} rule={rule} />
          )}

          <PolicyChangeDemo from={selected.from} to={selected.to} />

          <p className="text-xs text-muted-foreground">
            Rules are evaluated in file order; the strictest outcome wins (DENY &gt; REQUIRE_VERIFICATION &gt;
            REQUIRE_APPROVAL &gt; ALLOW).
          </p>
        </div>
      )}
    </>
  );
}
