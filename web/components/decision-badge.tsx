import { Ban, CircleCheck, Hourglass, ShieldQuestion, type LucideIcon } from "lucide-react";
import type { DecisionOutcome } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const OUTCOME_META: Record<
  DecisionOutcome,
  { label: string; icon: LucideIcon; className: string }
> = {
  ALLOW: {
    label: "Allowed",
    icon: CircleCheck,
    className:
      "border-emerald-600/30 bg-emerald-50 text-emerald-800 dark:border-emerald-400/30 dark:bg-emerald-950/60 dark:text-emerald-300",
  },
  REQUIRE_APPROVAL: {
    label: "Needs approval",
    icon: Hourglass,
    className:
      "border-amber-600/30 bg-amber-50 text-amber-900 dark:border-amber-400/30 dark:bg-amber-950/60 dark:text-amber-300",
  },
  REQUIRE_VERIFICATION: {
    label: "Needs verification",
    icon: ShieldQuestion,
    className:
      "border-sky-600/30 bg-sky-50 text-sky-900 dark:border-sky-400/30 dark:bg-sky-950/60 dark:text-sky-300",
  },
  DENY: {
    label: "Denied",
    icon: Ban,
    className:
      "border-red-600/30 bg-red-50 text-red-800 dark:border-red-400/30 dark:bg-red-950/60 dark:text-red-300",
  },
};

export function DecisionBadge({
  outcome,
  size = "default",
  className,
}: {
  outcome: DecisionOutcome;
  size?: "default" | "sm";
  className?: string;
}) {
  const meta = OUTCOME_META[outcome];
  const Icon = meta.icon;
  return (
    <span
      data-outcome={outcome}
      title={meta.label}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-md border font-mono font-semibold tracking-tight whitespace-nowrap",
        size === "sm" ? "px-1.5 py-0 text-[11px]" : "px-2 py-0.5 text-xs",
        meta.className,
        className,
      )}
    >
      <Icon aria-hidden className={size === "sm" ? "size-3" : "size-3.5"} />
      {outcome}
      <span className="sr-only"> ({meta.label})</span>
    </span>
  );
}
