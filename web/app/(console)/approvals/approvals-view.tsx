"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, ExternalLink, X } from "lucide-react";
import { toast } from "sonner";
import { DecisionBadge } from "@/components/decision-badge";
import { FactsSnapshot } from "@/components/facts-snapshot";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page";
import { RuleResultsTable } from "@/components/rule-results-table";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { glassVariants, SegmentedTabs } from "@/components/ui/glass";
import { Textarea } from "@/components/ui/textarea";
import type { Approval, ApprovalResolution, ApprovalStatus } from "@/lib/api/types";
import { useApprovals, useResolveApproval } from "@/lib/api/queries";
import { decidingRules } from "@/lib/decisions";
import { ACTION_LABELS, describeArgs } from "@/lib/events";
import { cn, formatDateTime } from "@/lib/utils";

const TABS: Array<{ value: ApprovalStatus; label: string }> = [
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

function ResolutionBadge({ status }: { status: ApprovalStatus }) {
  if (status === "pending") return <DecisionBadge outcome="REQUIRE_APPROVAL" size="sm" />;
  return (
    <span
      className={
        status === "approved"
          ? "inline-flex items-center gap-1 rounded-full border border-emerald-600/30 px-2 text-[11px] font-semibold text-emerald-800 uppercase dark:border-emerald-300/30 dark:text-emerald-200"
          : "inline-flex items-center gap-1 rounded-full border border-rose-600/30 px-2 text-[11px] font-semibold text-rose-800 uppercase dark:border-rose-300/30 dark:text-rose-200"
      }
    >
      {status === "approved" ? <Check aria-hidden className="size-3" /> : <X aria-hidden className="size-3" />}
      {status}
    </span>
  );
}

export function ApprovalDrawer({
  approval,
  onOpenChange,
  onResolve,
  resolving,
}: {
  approval: Approval | null;
  onOpenChange: (open: boolean) => void;
  onResolve: (approval: Approval, resolution: ApprovalResolution, note: string) => void;
  resolving: boolean;
}) {
  const [note, setNote] = useState("");

  return (
    <Sheet
      open={approval !== null}
      onOpenChange={(open) => {
        if (!open) setNote("");
        onOpenChange(open);
      }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl data-[side=right]:sm:max-w-xl">
        {approval && (
          <>
            <SheetHeader>
              <SheetTitle>
                {ACTION_LABELS[approval.intent.args.action]} · {describeArgs(approval.intent.args)}
              </SheetTitle>
              <SheetDescription>
                <span className="font-mono">{approval.approval_id}</span> · requested {formatDateTime(approval.requested_at)} UTC
              </SheetDescription>
            </SheetHeader>

            <div className="space-y-5 px-5 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <ResolutionBadge status={approval.status} />
                <Link
                  href={`/conversations/${approval.conversation_id}`}
                  className="inline-flex items-center gap-1 text-xs text-primary underline underline-offset-2"
                >
                  Conversation <span className="font-mono">{approval.conversation_id}</span>
                  <ExternalLink aria-hidden className="size-3" />
                </Link>
              </div>

              <section>
                <h3 className="mb-1 text-xs font-medium text-muted-foreground uppercase">Intent</h3>
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 rounded-xl border border-glass-edge bg-glass-inset p-3 font-mono text-xs">
                  {Object.entries(approval.intent.args).map(([k, v]) => (
                    <div key={k} className="contents">
                      <dt className="text-muted-foreground">{k}</dt>
                      <dd className="break-words">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
                    </div>
                  ))}
                  <dt className="text-muted-foreground">customer_id</dt>
                  <dd>{approval.intent.customer_id ?? "—"}</dd>
                  <dt className="text-muted-foreground">idempotency_key</dt>
                  <dd className="break-all">{approval.intent.idempotency_key}</dd>
                </dl>
                <p className="mt-2 text-xs text-muted-foreground">
                  Agent justification (not a fact): “{approval.intent.justification}”
                </p>
              </section>

              <section>
                <h3 className="mb-1 text-xs font-medium text-muted-foreground uppercase">
                  Decision · {approval.decision.policy_set} v{approval.decision.policy_version}
                </h3>
                <RuleResultsTable decision={approval.decision} />
              </section>

              <section>
                <h3 className="mb-1 text-xs font-medium text-muted-foreground uppercase">Facts snapshot</h3>
                <FactsSnapshot facts={approval.decision.facts_snapshot} />
              </section>

              {approval.status !== "pending" && (
                <section className="rounded-xl border border-glass-edge bg-glass-inset p-3 text-xs">
                  <p>
                    <span className="font-medium capitalize">{approval.status}</span> by {approval.reviewer ?? "—"}
                    {approval.resolved_at && <> on {formatDateTime(approval.resolved_at)} UTC</>}
                  </p>
                  {approval.note && <p className="mt-1 text-muted-foreground">“{approval.note}”</p>}
                </section>
              )}
            </div>

            {approval.status === "pending" && (
              <SheetFooter className="border-t">
                <Label htmlFor="review-note">Reviewer note (optional)</Label>
                <Textarea
                  id="review-note"
                  rows={3}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Verified photo of damage"
                />
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="destructive"
                    disabled={resolving}
                    onClick={() => onResolve(approval, "rejected", note)}
                  >
                    <X aria-hidden /> Reject
                  </Button>
                  <Button disabled={resolving} onClick={() => onResolve(approval, "approved", note)}>
                    <Check aria-hidden /> Approve
                  </Button>
                </div>
              </SheetFooter>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export function ApprovalsView() {
  const [tab, setTab] = useState<ApprovalStatus>("pending");
  const [selected, setSelected] = useState<Approval | null>(null);
  const { data, error, isPending, refetch } = useApprovals(tab);
  const all = useApprovals();
  const counts = (all.data?.items ?? []).reduce<Record<ApprovalStatus, number>>(
    (acc, a) => ({ ...acc, [a.status]: acc[a.status] + 1 }),
    { pending: 0, approved: 0, rejected: 0 },
  );

  const resolve = useResolveApproval({
    onSuccess: (a) => toast.success(`Approval ${a.status}`, { description: a.approval_id }),
    onConflict: (err) => toast.warning("Already resolved", { description: `${err.message} The queue has been refreshed.` }),
    onError: (err) => toast.error("Couldn't resolve approval — changes rolled back", { description: err.message }),
  });

  function onResolve(approval: Approval, resolution: ApprovalResolution, note: string) {
    setSelected(null);
    resolve.mutate({ approval, resolution, note });
  }

  return (
    <>
      <PageHeader
        title="Approvals"
        description="Actions the policy engine marked REQUIRE_APPROVAL wait here for a human decision."
      />

      <SegmentedTabs
        value={tab}
        onValueChange={setTab}
        layoutId="approvals-tab"
        className="mb-5"
        items={TABS.map((t) => ({
          value: t.value,
          label: (
            <>
              {t.label}
              <span className="ml-1 rounded-full bg-foreground/10 px-1.5 text-[11px] tabular-nums">{counts[t.value]}</span>
            </>
          ),
        }))}
      />

      {isPending ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : data.items.length === 0 ? (
        <EmptyState>No {tab} approvals.</EmptyState>
      ) : (
        <ul className="space-y-2" aria-label={`${tab} approvals`}>
          {data.items.map((a) => {
            const deciding = decidingRules(a.decision);
            return (
              <li key={a.approval_id}>
                <button
                  type="button"
                  onClick={() => setSelected(a)}
                  className={cn(
                    glassVariants({ radius: "2xl", interactive: true }),
                    "flex w-full flex-wrap items-center gap-x-4 gap-y-1.5 px-5 py-4 text-left hover:bg-glass-strong focus-visible:outline-2 focus-visible:outline-ring",
                  )}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium">
                      {ACTION_LABELS[a.intent.args.action]}{" "}
                      <span className="font-normal text-muted-foreground">· {describeArgs(a.intent.args)}</span>
                    </span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {deciding.map((r) => r.message).join(" · ")}
                    </span>
                  </span>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {deciding.map((r) =>
                      r.reason_code ? (
                        <code key={r.rule_id} className="rounded-md border px-1.5 py-0.5 font-mono">
                          {r.reason_code}
                        </code>
                      ) : null,
                    )}
                    <ResolutionBadge status={a.status} />
                    <time dateTime={a.requested_at}>{formatDateTime(a.requested_at)}</time>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <ApprovalDrawer
        approval={selected}
        onOpenChange={(open) => !open && setSelected(null)}
        onResolve={onResolve}
        resolving={resolve.isPending}
      />

      <p className="mt-6 text-xs text-muted-foreground">
        <Link href="/conversations" className={buttonVariants({ variant: "link", size: "xs" })}>
          Browse conversations
        </Link>
      </p>
    </>
  );
}
