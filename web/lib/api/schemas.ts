/**
 * Zod mirrors of docs/contracts/api.md. The Pydantic models in src/psa/domain/
 * are the source of truth; field names, enums and constraints follow them exactly.
 */
import { z } from "zod";

const isoDateTime = z.iso.datetime({ offset: true });
const jsonObject = z.record(z.string(), z.unknown());
const rate = z.number().min(0).max(1);

// ---------------------------------------------------------------- errors

export const ApiErrorEnvelopeSchema = z.object({
  error: z.object({ code: z.string(), message: z.string() }),
});

// ---------------------------------------------------------------- enums

export const ActionNameSchema = z.enum([
  "issue_refund",
  "issue_store_credit",
  "cancel_order",
  "update_address",
  "create_ticket",
  "escalate_to_human",
  "schedule_follow_up",
]);

export const DecisionOutcomeSchema = z.enum([
  "ALLOW",
  "REQUIRE_APPROVAL",
  "REQUIRE_VERIFICATION",
  "DENY",
]);

export const ReasonCodeSchema = z.enum([
  "OUTSIDE_RETURN_WINDOW",
  "ORDER_NOT_DELIVERED",
  "ORDER_ALREADY_SHIPPED",
  "ORDER_ALREADY_CANCELLED",
  "AMOUNT_EXCEEDS_REFUNDABLE",
  "HIGH_VALUE_REFUND",
  "STORE_CREDIT_LIMIT",
  "FINAL_SALE_ITEM",
  "GIFT_CARD_NOT_REFUNDABLE",
  "ITEM_NOT_IN_ORDER",
  "FOLLOW_UP_OUT_OF_RANGE",
  "IDENTITY_NOT_VERIFIED",
  "ORDER_NOT_OWNED_BY_CUSTOMER",
  "ORDER_NOT_FOUND",
  "MISSING_FACT",
  "NO_APPLICABLE_RULE",
  "DUPLICATE_REQUEST",
  "ADDRESS_CHANGE_AFTER_SHIPMENT",
  "ADDRESS_COUNTRY_CHANGE",
]);

export const EventTypeSchema = z.enum([
  "conversation_started",
  "user_message",
  "agent_message",
  "tool_call",
  "tool_result",
  "model_call",
  "action_proposed",
  "policy_decision",
  "verification_requested",
  "verification_completed",
  "approval_requested",
  "approval_resolved",
  "action_executed",
  "action_failed",
  "follow_up_scheduled",
  "follow_up_fired",
  "conversation_ended",
]);

export const EscalationPrioritySchema = z.enum(["low", "normal", "high", "urgent"]);
export const ConversationStatusSchema = z.enum(["active", "ended", "awaiting_approval"]);
export const ApprovalStatusSchema = z.enum(["pending", "approved", "rejected"]);
export const ApprovalResolutionSchema = z.enum(["approved", "rejected"]);
export const SystemUnderTestSchema = z.enum(["baseline", "guarded"]);
export const ScenarioCategorySchema = z.enum([
  "happy_path",
  "policy_boundary",
  "policy_bait",
  "prompt_injection",
  "identity",
  "stale_policy",
  "tool_failure",
  "idempotency",
  "multi_intent",
  "escalation",
  "follow_up",
]);

// ---------------------------------------------------------------- commerce

export const AddressSchema = z.object({
  line1: z.string().min(1),
  line2: z.string().nullable().default(null),
  city: z.string().min(1),
  region: z.string().min(2),
  postal_code: z.string().min(3),
  country: z.string().length(2),
});

// ---------------------------------------------------------------- actions

const reason = z.string().min(1).max(500);

export const IssueRefundArgsSchema = z.object({
  action: z.literal("issue_refund"),
  order_id: z.string(),
  amount_cents: z.number().int().positive(),
  item_skus: z.array(z.string()).default([]),
  reason,
});

export const IssueStoreCreditArgsSchema = z.object({
  action: z.literal("issue_store_credit"),
  customer_id: z.string(),
  order_id: z.string().nullable().default(null),
  amount_cents: z.number().int().positive(),
  reason,
});

export const CancelOrderArgsSchema = z.object({
  action: z.literal("cancel_order"),
  order_id: z.string(),
  reason,
});

export const UpdateAddressArgsSchema = z.object({
  action: z.literal("update_address"),
  order_id: z.string(),
  new_address: AddressSchema,
});

export const CreateTicketArgsSchema = z.object({
  action: z.literal("create_ticket"),
  order_id: z.string().nullable().default(null),
  subject: z.string().min(1).max(200),
  body: z.string().min(1).max(4000),
});

export const EscalateToHumanArgsSchema = z.object({
  action: z.literal("escalate_to_human"),
  reason,
  priority: EscalationPrioritySchema.default("normal"),
});

export const ScheduleFollowUpArgsSchema = z.object({
  action: z.literal("schedule_follow_up"),
  due_at: isoDateTime,
  order_id: z.string().nullable().default(null),
  note: z.string().min(1).max(1000),
});

export const ActionArgsSchema = z.discriminatedUnion("action", [
  IssueRefundArgsSchema,
  IssueStoreCreditArgsSchema,
  CancelOrderArgsSchema,
  UpdateAddressArgsSchema,
  CreateTicketArgsSchema,
  EscalateToHumanArgsSchema,
  ScheduleFollowUpArgsSchema,
]);

export const ActionIntentSchema = z.object({
  intent_id: z.string().regex(/^int_[A-Za-z0-9]{8,}$/),
  conversation_id: z.string(),
  customer_id: z.string().nullable().default(null),
  args: ActionArgsSchema,
  justification: z.string().min(1).max(1000),
  proposed_at: isoDateTime,
  idempotency_key: z.string().min(8),
});

// ---------------------------------------------------------------- decisions

export const RuleResultSchema = z.object({
  rule_id: z.string(),
  outcome: DecisionOutcomeSchema,
  reason_code: ReasonCodeSchema.nullable().default(null),
  message: z.string(),
});

export const DecisionSchema = z.object({
  intent_id: z.string(),
  outcome: DecisionOutcomeSchema,
  rule_results: z.array(RuleResultSchema),
  policy_set: z.string(),
  policy_version: z.string(),
  evaluated_at: isoDateTime,
  facts_snapshot: jsonObject,
});

// ---------------------------------------------------------------- events

export const MessagePayloadSchema = z.object({ text: z.string() });
export const ToolCallPayloadSchema = z.object({
  call_id: z.string(),
  tool: z.string(),
  args: jsonObject,
});
export const ToolResultPayloadSchema = z.object({
  call_id: z.string(),
  ok: z.boolean(),
  result: jsonObject.nullable(),
  error: z.string().nullable(),
  latency_ms: z.number().nonnegative(),
});
export const ModelCallPayloadSchema = z.object({
  model: z.string(),
  input_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(),
  latency_ms: z.number().nonnegative(),
  cost_usd: z.number().nonnegative(),
});
export const ActionProposedPayloadSchema = z.object({ intent: ActionIntentSchema });
export const PolicyDecisionPayloadSchema = z.object({ decision: DecisionSchema });
export const ApprovalRequestedPayloadSchema = z.object({
  approval_id: z.string(),
  intent_id: z.string(),
});
export const ApprovalResolvedPayloadSchema = z.object({
  approval_id: z.string(),
  resolution: ApprovalResolutionSchema,
  reviewer: z.string(),
  note: z.string().nullable(),
});
export const ActionExecutedPayloadSchema = z.object({
  intent_id: z.string(),
  idempotency_key: z.string(),
  result: jsonObject,
});
export const ActionFailedPayloadSchema = z.object({
  intent_id: z.string(),
  error: z.string(),
  retryable: z.boolean(),
  attempt: z.number().int().nonnegative(),
});
export const FollowUpScheduledPayloadSchema = z.object({
  follow_up_id: z.string(),
  due_at: isoDateTime,
  note: z.string(),
});
export const FollowUpFiredPayloadSchema = z.object({ follow_up_id: z.string() });

const eventBase = {
  event_id: z.string().regex(/^evt_[A-Za-z0-9]{8,}$/),
  conversation_id: z.string(),
  seq: z.number().int().nonnegative(),
  at: isoDateTime,
  policy_version: z.string().nullable().default(null),
};

function eventOf<T extends z.infer<typeof EventTypeSchema>, P extends z.ZodType>(
  type: T,
  payload: P,
) {
  return z.object({ ...eventBase, type: z.literal(type), payload });
}

const untypedPayload = jsonObject.default({});

export const EventSchema = z.discriminatedUnion("type", [
  eventOf("conversation_started", untypedPayload),
  eventOf("user_message", MessagePayloadSchema),
  eventOf("agent_message", MessagePayloadSchema),
  eventOf("tool_call", ToolCallPayloadSchema),
  eventOf("tool_result", ToolResultPayloadSchema),
  eventOf("model_call", ModelCallPayloadSchema),
  eventOf("action_proposed", ActionProposedPayloadSchema),
  eventOf("policy_decision", PolicyDecisionPayloadSchema),
  eventOf("verification_requested", untypedPayload),
  eventOf("verification_completed", untypedPayload),
  eventOf("approval_requested", ApprovalRequestedPayloadSchema),
  eventOf("approval_resolved", ApprovalResolvedPayloadSchema),
  eventOf("action_executed", ActionExecutedPayloadSchema),
  eventOf("action_failed", ActionFailedPayloadSchema),
  eventOf("follow_up_scheduled", FollowUpScheduledPayloadSchema),
  eventOf("follow_up_fired", FollowUpFiredPayloadSchema),
  eventOf("conversation_ended", untypedPayload),
]);

// ---------------------------------------------------------------- auth & health

export const LoginRequestSchema = z.object({ passcode: z.string().min(1) });
export const LoginResponseSchema = z.object({ token: z.string().min(1), expires_at: isoDateTime });

export const HealthSchema = z.object({
  status: z.string(),
  version: z.string(),
  policy_version: z.string(),
});

// ---------------------------------------------------------------- conversations

export const CreateConversationRequestSchema = z.object({
  customer_email: z.email().optional(),
});
export const CreateConversationResponseSchema = z.object({
  conversation_id: z.string(),
  started_at: isoDateTime,
});

export const ConversationSummarySchema = z.object({
  conversation_id: z.string(),
  started_at: isoDateTime,
  last_event_at: isoDateTime,
  customer_id: z.string().nullable(),
  status: ConversationStatusSchema,
  message_count: z.number().int().nonnegative(),
  actions_executed: z.number().int().nonnegative(),
  actions_blocked: z.number().int().nonnegative(),
});

export const ConversationListSchema = z.object({
  items: z.array(ConversationSummarySchema),
  next_cursor: z.string().nullable(),
});

export const SendMessageRequestSchema = z.object({ text: z.string().min(1) });
export const SendMessageResponseSchema = z.object({
  reply: z.object({ text: z.string(), at: isoDateTime }),
  events: z.array(EventSchema),
  pending_approval_id: z.string().nullable(),
});

export const ConversationEventsSchema = z.object({
  conversation_id: z.string(),
  events: z.array(EventSchema),
});

// ---------------------------------------------------------------- approvals

export const ApprovalSchema = z.object({
  approval_id: z.string(),
  conversation_id: z.string(),
  status: ApprovalStatusSchema,
  requested_at: isoDateTime,
  intent: ActionIntentSchema,
  decision: DecisionSchema,
  resolved_at: isoDateTime.nullable(),
  reviewer: z.string().nullable(),
  note: z.string().nullable(),
});

export const ApprovalListSchema = z.object({ items: z.array(ApprovalSchema) });

export const ResolveApprovalRequestSchema = z.object({
  resolution: ApprovalResolutionSchema,
  note: z.string().nullable().optional(),
});

// ---------------------------------------------------------------- policies

export const PolicySummarySchema = z.object({
  policy_set: z.string(),
  version: z.string(),
  rule_count: z.number().int().nonnegative(),
  updated_at: isoDateTime,
});
export const PolicyListSchema = z.object({ items: z.array(PolicySummarySchema) });

export const PolicyDetailSchema = z.object({
  policy_set: z.string(),
  version: z.string(),
  yaml: z.string(),
  rules: z.array(
    z.object({
      id: z.string(),
      applies_to: z.array(ActionNameSchema),
      description: z.string(),
    }),
  ),
});

// ---------------------------------------------------------------- evals

export const HeadlineMetricsSchema = z.object({
  task_success_rate: rate,
  unauthorized_action_rate: rate,
});

export const EvalRunSummarySchema = z.object({
  run_id: z.string(),
  suite: z.string(),
  started_at: isoDateTime,
  finished_at: isoDateTime,
  git_sha: z.string(),
  policy_version: z.string(),
  headline: z.object({ baseline: HeadlineMetricsSchema, guarded: HeadlineMetricsSchema }),
});
export const EvalRunListSchema = z.object({ items: z.array(EvalRunSummarySchema) });

export const TrialResultSchema = z.object({
  trial: z.number().int().nonnegative(),
  success: z.boolean(),
  unauthorized_actions: z.array(ActionNameSchema).default([]),
  false_refusal: z.boolean().default(false),
  escalated: z.boolean().default(false),
  turns: z.number().int().nonnegative(),
  latency_ms_p50: z.number().nonnegative(),
  latency_ms_p95: z.number().nonnegative(),
  cost_usd: z.number().nonnegative(),
  conversation_id: z.string(),
  failure_reason: z.string().nullable().default(null),
});

export const ScenarioResultSchema = z.object({
  scenario_id: z.string(),
  category: ScenarioCategorySchema,
  system: SystemUnderTestSchema,
  trials: z.array(TrialResultSchema),
});

export const SystemMetricsSchema = z.object({
  system: SystemUnderTestSchema,
  scenarios: z.number().int().nonnegative(),
  trials_per_scenario: z.number().int().nonnegative(),
  task_success_rate: rate,
  unauthorized_action_rate: rate,
  false_refusal_rate: rate,
  correct_escalation_rate: rate,
  injection_resistance_rate: rate,
  duplicate_side_effects: z.number().int().nonnegative(),
  pass_hat_k: z.record(z.string().regex(/^\d+$/), rate),
  latency_ms_p50: z.number().nonnegative(),
  latency_ms_p95: z.number().nonnegative(),
  cost_usd_per_resolved: z.number().nonnegative(),
  by_category: z.partialRecord(ScenarioCategorySchema, rate),
});

export const EvalRunReportSchema = z.object({
  run_id: z.string(),
  suite: z.string(),
  started_at: isoDateTime,
  finished_at: isoDateTime,
  git_sha: z.string(),
  policy_version: z.string(),
  agent_model: z.string(),
  simulator_model: z.string(),
  systems: z.array(SystemMetricsSchema),
  scenarios: z.array(ScenarioResultSchema),
});
