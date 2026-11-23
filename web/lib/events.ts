import type { ActionArgs, ActionIntent, Decision, Event, EventOf, EventType } from "@/lib/api/types";
import { formatCents, formatDateTime } from "@/lib/utils";

export interface ActionView {
  intent: ActionIntent;
  proposedSeq: number;
  decision: Decision | null;
  decisionSeq: number | null;
  executed: EventOf<"action_executed"> | null;
  failed: EventOf<"action_failed"> | null;
  approvalId: string | null;
  approvalResolution: "approved" | "rejected" | null;
}

/** Join proposals with their decision, approval and execution by intent_id. */
export function extractActions(events: Event[]): ActionView[] {
  const views = new Map<string, ActionView>();
  const approvalToIntent = new Map<string, string>();
  for (const e of events) {
    switch (e.type) {
      case "action_proposed":
        views.set(e.payload.intent.intent_id, {
          intent: e.payload.intent,
          proposedSeq: e.seq,
          decision: null,
          decisionSeq: null,
          executed: null,
          failed: null,
          approvalId: null,
          approvalResolution: null,
        });
        break;
      case "policy_decision": {
        const v = views.get(e.payload.decision.intent_id);
        if (v) {
          v.decision = e.payload.decision;
          v.decisionSeq = e.seq;
        }
        break;
      }
      case "approval_requested": {
        const v = views.get(e.payload.intent_id);
        if (v) v.approvalId = e.payload.approval_id;
        approvalToIntent.set(e.payload.approval_id, e.payload.intent_id);
        break;
      }
      case "approval_resolved": {
        const intentId = approvalToIntent.get(e.payload.approval_id);
        const v = intentId ? views.get(intentId) : undefined;
        if (v) v.approvalResolution = e.payload.resolution;
        break;
      }
      case "action_executed": {
        const v = views.get(e.payload.intent_id);
        if (v) v.executed = e;
        break;
      }
      case "action_failed": {
        const v = views.get(e.payload.intent_id);
        if (v) v.failed = e;
        break;
      }
    }
  }
  return [...views.values()];
}

export const ACTION_LABELS: Record<ActionArgs["action"], string> = {
  issue_refund: "Issue refund",
  issue_store_credit: "Issue store credit",
  cancel_order: "Cancel order",
  update_address: "Update address",
  create_ticket: "Create ticket",
  escalate_to_human: "Escalate to human",
  schedule_follow_up: "Schedule follow-up",
};

export function describeArgs(args: ActionArgs): string {
  switch (args.action) {
    case "issue_refund":
      return `${formatCents(args.amount_cents)} on ${args.order_id}`;
    case "issue_store_credit":
      return `${formatCents(args.amount_cents)} to ${args.customer_id}`;
    case "cancel_order":
      return args.order_id;
    case "update_address":
      return `${args.order_id} → ${args.new_address.city}, ${args.new_address.region} ${args.new_address.country}`;
    case "create_ticket":
      return args.subject;
    case "escalate_to_human":
      return `${args.priority} priority`;
    case "schedule_follow_up":
      return `due ${formatDateTime(args.due_at)} UTC`;
  }
}

export const EVENT_LABELS: Record<EventType, string> = {
  conversation_started: "Conversation started",
  user_message: "User message",
  agent_message: "Agent message",
  tool_call: "Tool call",
  tool_result: "Tool result",
  model_call: "Model call",
  action_proposed: "Action proposed",
  policy_decision: "Policy decision",
  verification_requested: "Verification requested",
  verification_completed: "Verification completed",
  approval_requested: "Approval requested",
  approval_resolved: "Approval resolved",
  action_executed: "Action executed",
  action_failed: "Action failed",
  follow_up_scheduled: "Follow-up scheduled",
  follow_up_fired: "Follow-up fired",
  conversation_ended: "Conversation ended",
};

export function summarizeEvent(e: Event): string {
  switch (e.type) {
    case "user_message":
    case "agent_message":
      return e.payload.text;
    case "tool_call":
      return `${e.payload.tool}(${Object.values(e.payload.args).join(", ")})`;
    case "tool_result":
      return e.payload.ok ? `ok · ${e.payload.latency_ms} ms` : `error: ${e.payload.error}`;
    case "model_call":
      return `${e.payload.input_tokens}→${e.payload.output_tokens} tokens · ${e.payload.latency_ms} ms`;
    case "action_proposed":
      return `${ACTION_LABELS[e.payload.intent.args.action]} · ${describeArgs(e.payload.intent.args)}`;
    case "policy_decision":
      return `${e.payload.decision.outcome} · ${e.payload.decision.rule_results.length} rules`;
    case "approval_requested":
      return e.payload.approval_id;
    case "approval_resolved":
      return `${e.payload.resolution} by ${e.payload.reviewer}`;
    case "action_executed":
      return e.payload.idempotency_key;
    case "action_failed":
      return `${e.payload.error} (attempt ${e.payload.attempt})`;
    case "follow_up_scheduled":
      return `due ${formatDateTime(e.payload.due_at)} UTC`;
    case "follow_up_fired":
      return e.payload.follow_up_id;
    default:
      return "";
  }
}
