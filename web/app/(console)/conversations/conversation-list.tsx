"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { ConversationStatusBadge } from "@/components/conversation-status";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/page";
import { GlassPanel } from "@/components/ui/glass";
import { useConversations } from "@/lib/api/queries";
import { formatDateTime } from "@/lib/utils";

export function ConversationList() {
  const { data, error, isPending, refetch } = useConversations();

  return (
    <>
      <PageHeader
        title="Conversations"
        description="Every conversation is an append-only event log. Open one to replay its decision trace."
      />
      {isPending ? (
        <LoadingState />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : data.items.length === 0 ? (
        <EmptyState>No conversations yet. Start one from the chat page.</EmptyState>
      ) : (
        <GlassPanel className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Conversations, most recent first</caption>
            <thead className="border-b text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-medium">Conversation</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
                <th scope="col" className="hidden px-4 py-2.5 font-medium sm:table-cell">Customer</th>
                <th scope="col" className="hidden px-4 py-2.5 font-medium md:table-cell">Last activity (UTC)</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Messages</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Executed</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Blocked</th>
                <th scope="col" className="w-8"><span className="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.conversation_id} className="group border-b transition-colors last:border-0 hover:bg-muted">
                  <td className="px-4 py-2.5">
                    <Link
                      href={`/conversations/${c.conversation_id}`}
                      className="font-mono text-xs font-medium underline-offset-2 group-hover:underline focus-visible:outline-2 focus-visible:outline-ring"
                    >
                      {c.conversation_id}
                    </Link>
                  </td>
                  <td className="px-4 py-2.5"><ConversationStatusBadge status={c.status} /></td>
                  <td className="hidden px-4 py-2.5 font-mono text-xs sm:table-cell">{c.customer_id ?? "—"}</td>
                  <td className="hidden px-4 py-2.5 text-xs text-muted-foreground md:table-cell">{formatDateTime(c.last_event_at)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">{c.message_count}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-emerald-700 dark:text-emerald-300">{c.actions_executed}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-rose-700 dark:text-rose-300">{c.actions_blocked}</td>
                  <td className="pr-3 text-muted-foreground"><ChevronRight aria-hidden className="size-4" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </GlassPanel>
      )}
    </>
  );
}
