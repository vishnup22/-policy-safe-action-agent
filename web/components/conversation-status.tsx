import type { ConversationStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const META: Record<ConversationStatus, { label: string; className: string }> = {
  active: { label: "Active", className: "border-sky-600/30 text-sky-800 dark:border-sky-300/30 dark:text-sky-200" },
  ended: { label: "Ended", className: "border-glass-edge text-muted-foreground" },
  awaiting_approval: {
    label: "Awaiting approval",
    className: "border-amber-600/30 text-amber-900 dark:border-amber-300/30 dark:text-amber-200",
  },
};

export function ConversationStatusBadge({ status }: { status: ConversationStatus }) {
  const meta = META[status];
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", meta.className)}>
      {meta.label}
    </span>
  );
}
