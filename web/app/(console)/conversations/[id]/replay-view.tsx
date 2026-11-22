"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  CircleCheckBig,
} from "lucide-react";
import { DecisionBadge } from "@/components/decision-badge";
import { FactsSnapshot, JsonBlock } from "@/components/facts-snapshot";
import { ErrorState, LoadingState, PageHeader } from "@/components/page";
import { RuleResultsTable } from "@/components/rule-results-table";
import { Button, buttonVariants } from "@/components/ui/button";
import { GlassPanel } from "@/components/ui/glass";
import type { Event, EventType } from "@/lib/api/types";
import { useConversationEvents } from "@/lib/api/queries";
import { ACTION_LABELS, EVENT_LABELS, describeArgs, extractActions, summarizeEvent } from "@/lib/events";
import { cn, formatDateTime, formatTime } from "@/lib/utils";

const TYPE_TONE: Partial<Record<EventType, string>> = {
  user_message: "bg-primary",
  agent_message: "bg-muted-foreground",
  action_proposed: "bg-violet-500",
  policy_decision: "bg-amber-500",
  action_executed: "bg-emerald-500",
  action_failed: "bg-red-500",
  approval_requested: "bg-amber-400",
  approval_resolved: "bg-amber-600",
  follow_up_scheduled: "bg-sky-500",
  follow_up_fired: "bg-sky-600",
};

function EventDetail({ event }: { event: Event }) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs text-muted-foreground">
          #{event.seq} · {formatDateTime(event.at)} UTC
        </p>
        <h2 className="text-base font-semibold">{EVENT_LABELS[event.type]}</h2>
        <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 font-mono text-xs">
          <dt className="text-muted-foreground">event_id</dt>
          <dd className="break-all">{event.event_id}</dd>
          <dt className="text-muted-foreground">policy_version</dt>
          <dd>{event.policy_version ?? "—"}</dd>
        </dl>
      </div>

      {(event.type === "user_message" || event.type === "agent_message") && (
        <p className="rounded-2xl border border-glass-edge bg-glass-inset px-3.5 py-2.5 text-sm">{event.payload.text}</p>
      )}

      {event.type === "action_proposed" && (
        <div className="space-y-2 text-sm">
          <p className="font-medium">
            {ACTION_LABELS[event.payload.intent.args.action]}{" "}
            <span className="font-normal text-muted-foreground">· {describeArgs(event.payload.intent.args)}</span>
          </p>
          <p className="text-xs text-muted-foreground">
            Idempotency key <code className="font-mono">{event.payload.intent.idempotency_key}</code>
          </p>
          <p className="rounded-xl border border-dashed border-glass-edge px-3 py-2 text-xs">
            <span className="font-medium">Agent justification</span> (never used as a policy fact): “
            {event.payload.intent.justification}”
          </p>
        </div>
      )}

      {event.type === "policy_decision" && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <DecisionBadge outcome={event.payload.decision.outcome} />
            <span className="text-muted-foreground">
              {event.payload.decision.policy_set}{" "}
              <span className="font-mono">v{event.payload.decision.policy_version}</span>
            </span>
          </div>
          <RuleResultsTable decision={event.payload.decision} />
          <div>
            <h3 className="mb-1 text-xs font-medium">Facts snapshot</h3>
            <FactsSnapshot facts={event.payload.decision.facts_snapshot} />
          </div>
        </div>
      )}

      {event.type === "tool_result" && typeof event.payload.result?.notes === "string" && (
        <div role="note" className="flex gap-2 rounded-xl border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-xs text-amber-950 dark:border-amber-300/25 dark:bg-amber-400/10 dark:text-amber-100">
          <AlertTriangle aria-hidden className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">Untrusted customer text in <code>notes</code></p>
            <p className="mt-0.5">“{event.payload.result.notes}”</p>
            <p className="mt-1">The policy engine never reads this field; decisions use system-of-record facts only.</p>
          </div>
        </div>
      )}

      <div>
        <h3 className="mb-1 text-xs font-medium">Raw payload</h3>
        <JsonBlock value={event.payload} label={`Payload of event ${event.seq}`} />
      </div>
    </div>
  );
}

export function ReplayView({ conversationId }: { conversationId: string }) {
  const { data, error, isPending, refetch } = useConversationEvents(conversationId);
  const events = useMemo(() => data?.events ?? [], [data]);
  const [hidden, setHidden] = useState<Set<EventType>>(new Set());
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const listRef = useRef<HTMLOListElement>(null);

  const visible = useMemo(() => events.filter((e) => !hidden.has(e.type)), [events, hidden]);
  const presentTypes = useMemo(() => [...new Set(events.map((e) => e.type))], [events]);
  const actions = useMemo(() => extractActions(events), [events]);
  const selected =
    visible.find((e) => e.seq === selectedSeq) ?? visible[0] ?? null;
  const index = selected ? visible.indexOf(selected) : -1;

  function step(delta: number) {
    if (visible.length === 0) return;
    const next = visible[Math.min(visible.length - 1, Math.max(0, index + delta))];
    setSelectedSeq(next.seq);
  }

  function jumpTo(seq: number) {
    const target = events.find((e) => e.seq === seq);
    if (target && hidden.has(target.type)) {
      setHidden((h) => {
        const n = new Set(h);
        n.delete(target.type);
        return n;
      });
    }
    setSelectedSeq(seq);
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        e.preventDefault();
        step(e.key === "ArrowLeft" ? -1 : 1);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    if (!selected) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-seq="${selected.seq}"]`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [selected]);

  function toggleType(t: EventType) {
    setHidden((h) => {
      const n = new Set(h);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });
  }

  const back = (
    <Link href="/conversations" className={buttonVariants({ variant: "ghost", size: "sm" })}>
      <ArrowLeft aria-hidden /> All conversations
    </Link>
  );

  if (isPending) return <LoadingState label="Loading event log…" />;
  if (error) return (<>{back}<ErrorState error={error} onRetry={() => void refetch()} /></>);

  const policyVersions = [...new Set(events.flatMap((e) => (e.policy_version ? [e.policy_version] : [])))];
  const executed = actions.filter((a) => a.executed);
  const notExecuted = actions.filter((a) => !a.executed);

  return (
    <>
      <div className="mb-2">{back}</div>
      <PageHeader
        title={<span className="font-mono text-lg">{conversationId}</span>}
        description={
          <>
            {events.length} events · policy {policyVersions.length ? policyVersions.join(", ") : "—"} · use ← / → to step
          </>
        }
      />

      <section aria-labelledby="executed-heading" className="mb-5 grid gap-3 md:grid-cols-2">
        <GlassPanel className="p-5">
          <h2 id="executed-heading" className="mb-2 text-sm font-semibold">Executed actions</h2>
          {executed.length === 0 ? (
            <p className="text-xs text-muted-foreground">No side effects were executed.</p>
          ) : (
            <ul className="space-y-2">
              {executed.map((a) => (
                <li key={a.intent.intent_id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                  <CircleCheckBig aria-hidden className="size-4 text-emerald-600 dark:text-emerald-300" />
                  <span className="font-medium">{ACTION_LABELS[a.intent.args.action]}</span>
                  <span className="text-muted-foreground">{describeArgs(a.intent.args)}</span>
                  {a.decisionSeq !== null && (
                    <button
                      type="button"
                      onClick={() => jumpTo(a.decisionSeq!)}
                      className="text-xs text-primary underline underline-offset-2"
                    >
                      allowed by decision #{a.decisionSeq}
                      {a.approvalId ? ` + approval ${a.approvalId}` : ""}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </GlassPanel>
        <GlassPanel className="p-5">
          <h2 className="mb-2 text-sm font-semibold">Blocked or pending actions</h2>
          {notExecuted.length === 0 ? (
            <p className="text-xs text-muted-foreground">None.</p>
          ) : (
            <ul className="space-y-2">
              {notExecuted.map((a) => (
                <li key={a.intent.intent_id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                  {a.decision && <DecisionBadge outcome={a.decision.outcome} size="sm" />}
                  <span className="font-medium">{ACTION_LABELS[a.intent.args.action]}</span>
                  <span className="text-muted-foreground">{describeArgs(a.intent.args)}</span>
                  {a.decisionSeq !== null && (
                    <button
                      type="button"
                      onClick={() => jumpTo(a.decisionSeq!)}
                      className="text-xs text-primary underline underline-offset-2"
                    >
                      decision #{a.decisionSeq}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </GlassPanel>
      </section>

      <fieldset className="mb-3">
        <legend className="mb-1.5 text-xs font-medium text-muted-foreground">Filter by event type</legend>
        <div className="flex flex-wrap gap-1.5">
          {presentTypes.map((t) => {
            const on = !hidden.has(t);
            return (
              <button
                key={t}
                type="button"
                aria-pressed={on}
                onClick={() => toggleType(t)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs transition-colors focus-visible:outline-2 focus-visible:outline-ring",
                  on ? "border-glass-edge-hover bg-accent text-foreground" : "border-glass-edge text-muted-foreground line-through",
                )}
              >
                {EVENT_LABELS[t]}
              </button>
            );
          })}
          {hidden.size > 0 && (
            <button type="button" onClick={() => setHidden(new Set())} className="px-2 text-xs text-primary underline">
              Show all
            </button>
          )}
        </div>
      </fieldset>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <GlassPanel as="section" aria-label="Event timeline" className="flex max-h-[70dvh] flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <span className="text-xs text-muted-foreground tabular-nums">
              {index + 1} / {visible.length}
            </span>
            <div className="flex gap-1">
              <Button variant="ghost" size="icon-sm" aria-label="Previous event" disabled={index <= 0} onClick={() => step(-1)}>
                <ChevronLeft aria-hidden />
              </Button>
              <Button variant="ghost" size="icon-sm" aria-label="Next event" disabled={index >= visible.length - 1} onClick={() => step(1)}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
          </div>
          <ol ref={listRef} className="flex-1 overflow-y-auto p-2">
            {visible.map((e) => {
              const active = selected?.seq === e.seq;
              return (
                <li key={e.event_id}>
                  <button
                    type="button"
                    data-seq={e.seq}
                    aria-current={active ? "step" : undefined}
                    onClick={() => setSelectedSeq(e.seq)}
                    className={cn(
                      "flex w-full items-start gap-2.5 rounded-xl px-2.5 py-2 text-left text-xs transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring",
                      active && "bg-accent shadow-[inset_0_1px_0_0_var(--glass-highlight)]",
                    )}
                  >
                    <span className="w-7 shrink-0 pt-px text-right font-mono text-muted-foreground tabular-nums">{e.seq}</span>
                    <span aria-hidden className={cn("mt-1.5 size-2 shrink-0 rounded-full", TYPE_TONE[e.type] ?? "bg-border")} />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="font-medium">{EVENT_LABELS[e.type]}</span>
                        <span className="shrink-0 font-mono text-[10px] text-muted-foreground">{formatTime(e.at)}</span>
                      </span>
                      <span className="mt-0.5 flex items-center gap-1.5 text-muted-foreground">
                        {e.type === "policy_decision" && <DecisionBadge outcome={e.payload.decision.outcome} size="sm" />}
                        <span className="truncate">{e.type === "policy_decision" ? `${e.payload.decision.rule_results.length} rules` : summarizeEvent(e)}</span>
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </GlassPanel>

        <GlassPanel as="section" aria-label="Event detail" aria-live="polite" className="p-5">
          {selected ? <EventDetail event={selected} /> : <p className="text-sm text-muted-foreground">No events match the filter.</p>}
        </GlassPanel>
      </div>
    </>
  );
}
