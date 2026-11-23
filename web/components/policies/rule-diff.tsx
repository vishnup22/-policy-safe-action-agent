"use client";

import { useEffect } from "react";
import { ArrowRight, Minus, PencilLine, Plus } from "lucide-react";
import { GlassPanel } from "@/components/ui/glass";
import { fieldChanges, formatScalar, isMissing, ruleLines, type LineChange, type RuleLine } from "@/lib/policy-diff";
import { cn } from "@/lib/utils";

export type RuleChangeKind = "changed" | "added" | "removed";

const KIND: Record<RuleChangeKind, { label: string; icon: typeof Plus; className: string }> = {
  changed: {
    label: "Changed",
    icon: PencilLine,
    className: "border-amber-600/30 text-amber-900 dark:border-amber-300/30 dark:text-amber-200",
  },
  added: {
    label: "Added",
    icon: Plus,
    className: "border-emerald-600/30 text-emerald-800 dark:border-emerald-300/30 dark:text-emerald-200",
  },
  removed: {
    label: "Removed",
    icon: Minus,
    className: "border-rose-600/30 text-rose-800 dark:border-rose-300/30 dark:text-rose-200",
  },
};

export function ChangeBadge({ kind }: { kind: RuleChangeKind }) {
  const { label, icon: Icon, className } = KIND[kind];
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase", className)}>
      <Icon aria-hidden className="size-3" />
      {label}
    </span>
  );
}

const LINE_TONE: Record<LineChange, string> = {
  same: "",
  changed: "",
  added: "bg-emerald-500/12 dark:bg-emerald-400/12",
  removed: "bg-rose-500/12 dark:bg-rose-400/12",
};

function lineTone(line: RuleLine, side: "before" | "after") {
  if (line.change === "changed") return side === "after" ? LINE_TONE.added : LINE_TONE.removed;
  return LINE_TONE[line.change];
}

function Marker({ line, side }: { line: RuleLine; side: "before" | "after" }) {
  if (line.change === "same") return <span aria-hidden className="w-4 shrink-0" />;
  const sign = side === "after" ? "+" : "−";
  const text = line.change === "changed" ? (side === "after" ? "new value: " : "old value: ") : side === "after" ? "added: " : "removed: ";
  return (
    <>
      <span aria-hidden className="w-4 shrink-0 text-center font-semibold text-muted-foreground">{sign}</span>
      <span className="sr-only">{text}</span>
    </>
  );
}

function RuleYaml({ lines, side, caption }: { lines: RuleLine[]; side: "before" | "after"; caption: string }) {
  return (
    <figure className="min-w-0">
      <figcaption className="mb-1.5 text-xs font-medium text-muted-foreground">{caption}</figcaption>
      <pre className="relative overflow-hidden rounded-2xl border border-glass-edge bg-glass-inset py-2 font-mono text-[12px] leading-relaxed">
        <code>
          {lines.map((line) => (
            <span
              key={line.path}
              data-path={line.path}
              data-change={line.change}
              className={cn("flex px-2", lineTone(line, side))}
            >
              <Marker line={line} side={side} />
              <span
                className="min-w-0 flex-1 break-words whitespace-pre-wrap"
                style={{ paddingLeft: `${line.depth * 2}ch` }}
              >
                {line.bullet && <span className="text-muted-foreground">- </span>}
                {line.key !== null && (
                  <>
                    <span className="text-sky-700 dark:text-sky-300">{line.key}</span>:
                  </>
                )}
                {line.value !== null && <span className={line.change === "same" ? "" : "font-semibold"}> {line.value}</span>}
              </span>
            </span>
          ))}
        </code>
      </pre>
    </figure>
  );
}

function FieldChangeList({ before, after }: { before: Record<string, unknown>; after: Record<string, unknown> }) {
  const changes = fieldChanges(before, after);
  return (
    <dl aria-label="Changed fields" className="mb-4 space-y-2 rounded-2xl border border-glass-edge bg-glass-inset p-3 text-sm">
      {changes.map((c) => (
        <div key={c.path} className="grid gap-1 sm:grid-cols-[minmax(8rem,auto)_minmax(0,1fr)] sm:gap-3">
          <dt className="font-mono text-xs font-medium text-muted-foreground sm:pt-0.5">{c.path}</dt>
          <dd className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
            {isMissing(c.before) ? (
              <span className="text-xs text-muted-foreground">(not set)</span>
            ) : (
              <del className="min-w-0 rounded bg-rose-500/12 px-1 font-mono text-xs break-words text-rose-900 decoration-rose-700/60 dark:bg-rose-400/12 dark:text-rose-200">
                <span className="sr-only">was </span>
                {formatScalar(c.before)}
              </del>
            )}
            <ArrowRight aria-hidden className="size-3 shrink-0 self-center text-muted-foreground" />
            {isMissing(c.after) ? (
              <span className="text-xs text-muted-foreground">(removed)</span>
            ) : (
              <ins className="min-w-0 rounded bg-emerald-500/12 px-1 font-mono text-xs break-words text-emerald-900 no-underline dark:bg-emerald-400/12 dark:text-emerald-200">
                <span className="sr-only">now </span>
                {formatScalar(c.after)}
              </ins>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function RuleDiffCard({
  id,
  kind,
  before,
  after,
  fromVersion,
  toVersion,
  highlighted = false,
}: {
  id: string;
  kind: RuleChangeKind;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  fromVersion: string;
  toVersion: string;
  highlighted?: boolean;
}) {
  const anchor = `rule-${id}`;
  useEffect(() => {
    if (highlighted) document.getElementById(anchor)?.scrollIntoView?.({ block: "center" });
  }, [highlighted, anchor]);

  const headingId = `${anchor}-heading`;
  return (
    <GlassPanel
      as="article"
      id={anchor}
      aria-labelledby={headingId}
      data-highlighted={highlighted || undefined}
      className={cn("scroll-mt-28 p-4 sm:p-6", highlighted && "ring-2 ring-ring ring-offset-2 ring-offset-background")}
    >
      <header className="mb-4 flex flex-wrap items-center gap-2">
        <h3 id={headingId} className="font-mono text-sm font-semibold">{id}</h3>
        <ChangeBadge kind={kind} />
        {highlighted && <span className="text-xs text-muted-foreground">Linked from a decision</span>}
      </header>
      {kind === "changed" && before && after && <FieldChangeList before={before} after={after} />}
      <div className={cn("grid gap-4", kind === "changed" && "lg:grid-cols-2")}>
        {before && (
          <RuleYaml
            side="before"
            caption={`${kind === "removed" ? "Removed from" : "Before"} · ${fromVersion}`}
            lines={ruleLines(before, "before", after)}
          />
        )}
        {after && (
          <RuleYaml
            side="after"
            caption={`${kind === "added" ? "Added in" : "After"} · ${toVersion}`}
            lines={ruleLines(after, "after", before)}
          />
        )}
      </div>
    </GlassPanel>
  );
}
