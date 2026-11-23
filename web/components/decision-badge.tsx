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
      "border-emerald-600/25 bg-emerald-50/80 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-400/10 dark:text-emerald-200",
  },
  REQUIRE_APPROVAL: {
    label: "Needs approval",
    icon: Hourglass,
    className:
      "border-amber-600/25 bg-amber-50/80 text-amber-900 dark:border-amber-300/25 dark:bg-amber-400/10 dark:text-amber-200",
  },
  REQUIRE_VERIFICATION: {
    label: "Needs verification",
    icon: ShieldQuestion,
    className:
      "border-sky-600/25 bg-sky-50/80 text-sky-900 dark:border-sky-300/25 dark:bg-sky-400/10 dark:text-sky-200",
  },
  DENY: {
    label: "Denied",
    icon: Ban,
    className:
      "border-rose-600/25 bg-rose-50/80 text-rose-800 dark:border-rose-300/25 dark:bg-rose-400/10 dark:text-rose-200",
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
        "inline-flex shrink-0 items-center gap-1 rounded-full border font-mono font-semibold tracking-tight whitespace-nowrap",
        size === "sm" ? "px-2 py-0 text-[11px]" : "px-2.5 py-0.5 text-xs",
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
