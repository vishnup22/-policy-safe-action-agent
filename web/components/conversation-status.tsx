import type { ConversationStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const META: Record<ConversationStatus, { label: string; className: string }> = {
  active: { label: "Active", className: "border-sky-500/40 text-sky-800 dark:text-sky-300" },
  ended: { label: "Ended", className: "border-border text-muted-foreground" },
  awaiting_approval: { label: "Awaiting approval", className: "border-amber-500/50 text-amber-900 dark:text-amber-300" },
};

export function ConversationStatusBadge({ status }: { status: ConversationStatus }) {
  const meta = META[status];
  return (
    <span className={cn("inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", meta.className)}>
      {meta.label}
    </span>
  );
}
