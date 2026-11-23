"use client";

import { useEffect, type ReactNode } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Bot,
  Check,
  ClipboardCheck,
  FileCode2,
  FlaskConical,
  History,
  Scale,
  ScrollText,
  TriangleAlert,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { DecisionBadge } from "@/components/decision-badge";
import { BlurFade, GlassPanel } from "@/components/ui/glass";
import type { Approval, DecisionOutcome, Event, SystemMetrics } from "@/lib/api/types";
import { useAuth } from "@/lib/auth";
import { decidingRules } from "@/lib/decisions";
import { ACTION_LABELS, EVENT_LABELS, describeArgs, summarizeEvent } from "@/lib/events";
import { loadLandingData, PREVIEW_CONVERSATION_ID, type DataSource, type LandingData } from "@/lib/landing";import { cn, formatPercent } from "@/lib/utils";
import { MiniPassHatK } from "./mini-pass-hat-k";

function useLandingData() {
  const { client } = useAuth();
  return useQuery({
    queryKey: ["landing", client.mode],
    queryFn: () => loadLandingData(client),
    staleTime: Infinity,
    retry: false,
  });
}

// ---------------------------------------------------------------- tile chrome

function Tile({
  title,
  icon: Icon,
  aside,
  className,
  delay = 0,
  id,
  children,
}: {
  title: string;
  icon: LucideIcon;
  aside?: ReactNode;
  className?: string;
  delay?: number;
  id?: string;
  children: ReactNode;
}) {
  const headingId = `tile-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  return (
    <BlurFade delay={delay} id={id} className={cn("scroll-mt-28", className)}>
      <GlassPanel as="article" spotlight aria-labelledby={headingId} className="flex h-full flex-col p-6 sm:p-7">
        <header className="mb-5 flex items-start justify-between gap-3">
          <h3 id={headingId} className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight">
            <span className="flex size-8 items-center justify-center rounded-xl border border-glass-edge bg-glass-inset shadow-[inset_0_1px_0_0_var(--glass-highlight)]">
              <Icon aria-hidden className="size-4" />
            </span>
            {title}
          </h3>
          {aside}
        </header>
        {children}
      </GlassPanel>
    </BlurFade>
  );
}

function SourceChip({ source }: { source: DataSource }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold uppercase",
        source === "live"
          ? "border-emerald-600/30 text-emerald-800 dark:border-emerald-300/30 dark:text-emerald-200"
          : "border-violet-600/30 text-violet-800 dark:border-violet-300/30 dark:text-violet-200",
      )}
      title={source === "live" ? "Loaded from the live API" : "API unavailable — showing the demo world"}
    >
      {source === "live" ? "Live API" : "Demo data"}
    </span>
  );
}

function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-2xl bg-muted motion-reduce:animate-none", className)} />;
}

function TileLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="mt-auto inline-flex items-center gap-1 self-start rounded-full pt-5 text-sm font-medium text-foreground underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      {children} <ArrowRight aria-hidden className="size-3.5" />
    </Link>
  );
}

// ---------------------------------------------------------------- architecture

const STEPS: Array<{ icon: LucideIcon; title: string; body: string }> = [
  { icon: Bot, title: "The model proposes", body: "Read tools and propose_action only. It never touches a write tool." },
  { icon: Scale, title: "Policy decides", body: "Versioned YAML, a closed operator set, facts from the system of record." },
  { icon: Zap, title: "Executor acts", body: "Approved actions run once: every side effect carries an idempotency key." },
];

const OUTCOMES: DecisionOutcome[] = ["DENY", "REQUIRE_VERIFICATION", "REQUIRE_APPROVAL", "ALLOW"];

function ArchitectureTile() {
  return (
    <Tile title="Propose → decide → execute" icon={Scale} className="md:col-span-2">
      <ol className="grid gap-3 sm:grid-cols-3">
        {STEPS.map(({ icon: Icon, title, body }, i) => (
          <li key={title} className="relative rounded-2xl border border-glass-edge bg-glass-inset p-4">
            <div className="flex items-center gap-2">
              <Icon aria-hidden className="size-4 text-muted-foreground" />
              <span className="font-mono text-[11px] text-muted-foreground">0{i + 1}</span>
            </div>
            <p className="mt-3 font-medium tracking-tight">{title}</p>
            <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
            {i < STEPS.length - 1 && (
              <ArrowRight
                aria-hidden
                className="absolute top-1/2 -right-3 z-10 hidden size-4 -translate-y-1/2 rounded-full bg-background text-muted-foreground sm:block"
              />
            )}
          </li>
        ))}
      </ol>
      <div className="mt-3 flex flex-col gap-3 rounded-2xl border border-glass-edge bg-glass-inset p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <ScrollText aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-medium text-foreground">Append-only event log.</span> Replay reproduces every decision
            with its policy version.
          </span>
        </p>
        <p className="flex flex-wrap items-center gap-1.5" aria-label="Decision precedence, strictest first">
          {OUTCOMES.map((o, i) => (
            <span key={o} className="inline-flex items-center gap-1.5">
              <DecisionBadge outcome={o} size="sm" />
              {i < OUTCOMES.length - 1 && <span aria-hidden className="text-xs text-muted-foreground">›</span>}
            </span>
          ))}
        </p>
      </div>
    </Tile>
  );
}

// ---------------------------------------------------------------- results

const RESULT_METRICS = [
  { key: "unauthorized_action_rate", label: "Unauthorized actions", better: "lower" },
  { key: "task_success_rate", label: "Task success", better: "higher" },
  { key: "false_refusal_rate", label: "False refusals", better: "lower" },
] as const satisfies ReadonlyArray<{ key: keyof SystemMetrics; label: string; better: "lower" | "higher" }>;

function Bar({ value, tone, label }: { value: number; tone: "baseline" | "guarded"; label: string }) {
  return (
    <div className="grid grid-cols-[4.5rem_minmax(0,1fr)_3.25rem] items-center gap-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="h-1.5 overflow-hidden rounded-full bg-muted">
        <span
          className={cn(
            "block h-full rounded-full",
            tone === "guarded" ? "bg-emerald-600 dark:bg-emerald-300" : "bg-foreground/35",
          )}
          style={{ width: `${Math.max(value * 100, 1.5)}%` }}
        />
      </span>
      <span className="text-right tabular-nums">{formatPercent(value, 1)}</span>
    </div>
  );
}

function ResultsTile({ data }: { data: LandingData | undefined }) {
  const r = data?.results;
  return (
    <Tile
      id="results"
      title="Baseline vs guarded"
      icon={FlaskConical}
      className="lg:row-span-2"
      delay={0.05}
      aside={r && <SourceChip source={r.source} />}
    >
      {!r ? (
        <div className="space-y-6" aria-busy="true">
          <span className="sr-only">Loading results…</span>
          {RESULT_METRICS.map((m) => (
            <Skeleton key={m.key} className="h-24" />
          ))}
        </div>
      ) : (
        <>
          <p className="-mt-2 mb-5 text-sm text-muted-foreground">
            Same scenarios, same model. The baseline gets the policy as prompt text; the guarded agent goes through the
            policy engine.
          </p>
          <dl className="space-y-6">
            {RESULT_METRICS.map((m) => {
              const Better = m.better === "lower" ? ArrowDown : ArrowUp;
              return (
                <div key={m.key}>
                  <dt className="flex items-center justify-between gap-2 text-sm font-medium">
                    {m.label}
                    <span className="flex items-center gap-0.5 text-[11px] font-normal text-muted-foreground">
                      <Better aria-hidden className="size-3" /> {m.better} is better
                    </span>
                  </dt>
                  <dd className="mt-1">
                    <span className="text-4xl font-semibold tracking-tight tabular-nums">{formatPercent(r.guarded[m.key], 1)}</span>
                    <span className="ml-2 text-sm text-muted-foreground">guarded</span>
                    <div className="mt-3 space-y-1.5">
                      <Bar value={r.baseline[m.key]} tone="baseline" label="Baseline" />
                      <Bar value={r.guarded[m.key]} tone="guarded" label="Guarded" />
                    </div>
                  </dd>
                </div>
              );
            })}
          </dl>
          <p className="mt-6 text-xs leading-relaxed text-muted-foreground">
            Run <span className="font-mono">{r.report.run_id}</span> · {r.report.suite} suite · {r.guarded.scenarios}{" "}
            scenarios × {r.guarded.trials_per_scenario} trials · policy{" "}
            <span className="font-mono">{r.report.policy_version}</span>
          </p>
          <TileLink href={`/evals/${r.report.run_id}`}>Full report</TileLink>
        </>
      )}
    </Tile>
  );
}

function PassHatKTile({ data }: { data: LandingData | undefined }) {
  const r = data?.results;
  return (
    <Tile
      title="pass^k — reliability"
      icon={FlaskConical}
      className="md:col-span-1 lg:col-span-2"
      delay={0.1}
      aside={
        <span className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="h-0 w-4 border-t-2 border-dashed" style={{ borderColor: "var(--chart-2)" }} />
            Baseline
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden className="h-0.5 w-4 rounded-full" style={{ background: "var(--chart-1)" }} />
            Guarded
          </span>
        </span>
      }
    >
      <p className="-mt-2 mb-4 text-sm text-muted-foreground">
        Probability that all k repeated trials of a scenario succeed. A flat line means the agent behaves the same way
        every time.
      </p>
      {r ? <MiniPassHatK baseline={r.baseline} guarded={r.guarded} /> : <Skeleton className="aspect-[36/17] w-full" />}
    </Tile>
  );
}

// ---------------------------------------------------------------- replay

const TRACE_TYPES = new Set(["user_message", "tool_result", "action_proposed", "policy_decision", "agent_message"]);

function TraceRow({ event }: { event: Event }) {
  const notes = event.type === "tool_result" && typeof event.payload.result?.notes === "string";
  return (
    <li className="relative grid grid-cols-[1.75rem_minmax(0,1fr)] gap-2 py-1.5">
      <span className="pt-0.5 text-right font-mono text-[11px] text-muted-foreground tabular-nums">{event.seq}</span>
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
          {EVENT_LABELS[event.type]}
          {event.type === "policy_decision" && <DecisionBadge outcome={event.payload.decision.outcome} size="sm" />}
          {notes && (
            <span className="inline-flex items-center gap-1 rounded-full border border-amber-600/30 px-1.5 text-[10px] font-semibold text-amber-900 dark:border-amber-300/30 dark:text-amber-200">
              <TriangleAlert aria-hidden className="size-3" /> untrusted note
            </span>
          )}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {event.type === "policy_decision"
            ? decidingRules(event.payload.decision).map((r) => r.reason_code ?? r.rule_id).join(" · ")
            : summarizeEvent(event)}
        </span>
      </span>
    </li>
  );
}

function ReplayTile({ data }: { data: LandingData | undefined }) {
  const events = (data?.trace ?? []).filter((e) => TRACE_TYPES.has(e.type)).slice(0, 6);
  return (
    <Tile id="replay" title="Replay a decision" icon={History} delay={0.05}>
      <p className="-mt-2 mb-3 text-sm text-muted-foreground">
        A prompt-injection attempt, step by step. The note in the order record never reaches the policy engine.
      </p>
      {data ? (
        <ol className="divide-y divide-border">{events.map((e) => <TraceRow key={e.event_id} event={e} />)}</ol>
      ) : (
        <Skeleton className="h-56" />
      )}
      <TileLink href={`/conversations/${PREVIEW_CONVERSATION_ID}`}>Open the replay</TileLink>
    </Tile>
  );
}

// ---------------------------------------------------------------- policy

function yamlValueTone(value: string) {
  if (/\bDENY\b/.test(value)) return "text-rose-700 dark:text-rose-300";
  if (/\bREQUIRE_(APPROVAL|VERIFICATION)\b/.test(value)) return "text-amber-800 dark:text-amber-200";
  if (/\bALLOW\b/.test(value)) return "text-emerald-700 dark:text-emerald-300";
  return "text-foreground";
}

function YamlLine({ line }: { line: string }) {
  if (/^\s*#/.test(line)) return <span className="text-muted-foreground">{line}</span>;
  const m = /^(\s*-?\s*)([A-Za-z_]+)(:)(.*)$/.exec(line);
  if (!m) return <>{line || " "}</>;
  return (
    <>
      {m[1]}
      <span className="text-sky-700 dark:text-sky-300">{m[2]}</span>
      {m[3]}
      <span className={yamlValueTone(m[4])}>{m[4]}</span>
    </>
  );
}

function PolicyTile({ data }: { data: LandingData | undefined }) {
  const policy = data?.policy;
  const lines = policy ? policy.detail.yaml.split(/\r?\n/).slice(0, 22) : [];
  return (
    <Tile
      title="Policy as code"
      icon={FileCode2}
      delay={0.1}
      aside={policy && <SourceChip source={policy.source} />}
    >
      <p className="-mt-2 mb-3 text-sm text-muted-foreground">
        Rules are data, not prompt text — no <code className="font-mono text-xs">eval()</code>, no free-form
        expressions.
      </p>
      {policy ? (
        <>
          <pre
            tabIndex={0}
            aria-label={`Excerpt of policy ${policy.detail.policy_set} version ${policy.detail.version}`}
            className="max-h-72 overflow-auto rounded-2xl border border-glass-edge bg-glass-inset p-4 font-mono text-[12px] leading-relaxed focus-visible:outline-2 focus-visible:outline-ring"
          >
            <code>
              {lines.map((line, i) => (
                <span key={i} className="block whitespace-pre">
                  <YamlLine line={line} />
                </span>
              ))}
            </code>
          </pre>
          <p className="mt-3 text-xs text-muted-foreground">
            {policy.detail.rules.length} rules · <span className="font-mono">{policy.detail.policy_set}</span> v
            {policy.detail.version}
          </p>
        </>
      ) : (
        <Skeleton className="h-72" />
      )}
    </Tile>
  );
}

// ---------------------------------------------------------------- approvals

function ApprovalRow({ approval }: { approval: Approval }) {
  const reason = decidingRules(approval.decision).find((r) => r.reason_code)?.reason_code;
  return (
    <li className="flex items-center justify-between gap-3 rounded-2xl border border-glass-edge bg-glass-inset px-3.5 py-3">
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">
          {ACTION_LABELS[approval.intent.args.action]}{" "}
          <span className="font-normal text-muted-foreground">· {describeArgs(approval.intent.args)}</span>
        </span>
        {reason && <code className="font-mono text-[11px] text-muted-foreground">{reason}</code>}
      </span>
      {approval.status === "pending" ? (
        <DecisionBadge outcome="REQUIRE_APPROVAL" size="sm" />
      ) : (
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 text-[11px] font-semibold uppercase",
            approval.status === "approved"
              ? "border-emerald-600/30 text-emerald-800 dark:border-emerald-300/30 dark:text-emerald-200"
              : "border-rose-600/30 text-rose-800 dark:border-rose-300/30 dark:text-rose-200",
          )}
        >
          {approval.status === "approved" ? <Check aria-hidden className="size-3" /> : <X aria-hidden className="size-3" />}
          {approval.status}
        </span>
      )}
    </li>
  );
}

function ApprovalsTile({ data }: { data: LandingData | undefined }) {
  const items = data
    ? [...data.approvals.items].sort((a, b) => Number(b.status === "pending") - Number(a.status === "pending")).slice(0, 3)
    : [];
  return (
    <Tile
      title="Human in the loop"
      icon={ClipboardCheck}
      className="md:col-span-2 lg:col-span-1"
      delay={0.15}
      aside={data && <SourceChip source={data.approvals.source} />}
    >
      <p className="-mt-2 mb-3 text-sm text-muted-foreground">
        High-value refunds and large credits wait for a reviewer. Approving executes exactly once.
      </p>
      {data ? (
        items.length ? (
          <ul className="space-y-2">{items.map((a) => <ApprovalRow key={a.approval_id} approval={a} />)}</ul>
        ) : (
          <p className="text-sm text-muted-foreground">The approvals queue is empty.</p>
        )
      ) : (
        <Skeleton className="h-48" />
      )}
      <TileLink href="/approvals">Review the queue</TileLink>
    </Tile>
  );
}

// ---------------------------------------------------------------- grid

export function Bento() {
  const { data, error } = useLandingData();

  // The grid mounts after first paint, so a deep link like /#results needs a scroll once its target exists.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) document.getElementById(id)?.scrollIntoView();
  }, []);

  return (
    <>
      {error && (
        <p role="alert" className="mb-4 text-center text-sm text-destructive">
          Couldn&apos;t load eval results: {error.message}
        </p>
      )}
      <div className="grid grid-flow-row-dense grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 lg:gap-6">
        <ArchitectureTile />
        <ResultsTile data={data} />
        <PassHatKTile data={data} />
        <ReplayTile data={data} />
        <PolicyTile data={data} />
        <ApprovalsTile data={data} />
      </div>
    </>
  );
}
