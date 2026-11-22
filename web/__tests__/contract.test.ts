/**
 * Every example in docs/contracts/api.md must parse with the Zod schemas.
 * Examples are copied verbatim; placeholder unions in the doc
 * (e.g. "active | ended | awaiting_approval") are replaced with one member.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import * as s from "@/lib/api/schemas";

const intent = {
  intent_id: "int_9x8y7z6w",
  conversation_id: "conv_8f3k2l1m",
  customer_id: "cus_k2m9x1",
  args: { action: "issue_refund", order_id: "ord_q1w2e3", amount_cents: 3200, item_skus: ["LG-MUG-014"], reason: "Arrived cracked" },
  justification: "Customer reports item damaged on arrival",
  proposed_at: "2026-11-21T12:00:03Z",
  idempotency_key: "idem_conv8f3k_refund_ord_q1w2e3",
};

const decision = {
  intent_id: "int_9x8y7z6w",
  outcome: "DENY",
  rule_results: [
    { rule_id: "IDENTITY_VERIFIED", outcome: "ALLOW", reason_code: null, message: "Identity verified" },
    { rule_id: "REFUND_WINDOW", outcome: "DENY", reason_code: "OUTSIDE_RETURN_WINDOW", message: "Delivered 41 days ago; return window is 30 days" },
  ],
  policy_set: "larkspur-returns",
  policy_version: "2026.11.21-1",
  evaluated_at: "2026-11-21T12:00:04Z",
  facts_snapshot: { "order.days_since_delivery": 41, "order.status": "delivered", "session.identity_verified": true },
};

const event = {
  event_id: "evt_a1b2c3d4",
  conversation_id: "conv_8f3k2l1m",
  seq: 7,
  type: "policy_decision",
  at: "2026-11-21T12:00:04Z",
  policy_version: "2026.11.21-1",
  payload: { decision },
};

describe("docs/contracts/api.md examples", () => {
  it("auth", () => {
    expect(s.LoginRequestSchema.parse({ passcode: "string" })).toBeTruthy();
    expect(s.LoginResponseSchema.parse({ token: "string", expires_at: "2026-11-22T12:00:00Z" }).token).toBe("string");
  });

  it("conversations", () => {
    expect(s.CreateConversationRequestSchema.parse({ customer_email: "maya.r@example.com" })).toBeTruthy();
    expect(s.CreateConversationRequestSchema.parse({})).toEqual({});
    expect(
      s.CreateConversationResponseSchema.parse({ conversation_id: "conv_8f3k2l1m", started_at: "2026-11-21T12:00:00Z" }),
    ).toBeTruthy();
    for (const status of ["active", "ended", "awaiting_approval"]) {
      const list = s.ConversationListSchema.parse({
        items: [
          {
            conversation_id: "conv_8f3k2l1m",
            started_at: "2026-11-21T12:00:00Z",
            last_event_at: "2026-11-21T12:03:10Z",
            customer_id: "cus_k2m9x1",
            status,
            message_count: 8,
            actions_executed: 1,
            actions_blocked: 2,
          },
        ],
        next_cursor: null,
      });
      expect(list.items[0].status).toBe(status);
    }
  });

  it("send message + events", () => {
    expect(s.SendMessageRequestSchema.parse({ text: "My mug arrived cracked, can I get a refund?" })).toBeTruthy();
    const res = s.SendMessageResponseSchema.parse({
      reply: { text: "I'm sorry about that...", at: "2026-11-21T12:00:05Z" },
      events: [event],
      pending_approval_id: null,
    });
    expect(res.events[0].type).toBe("policy_decision");
    expect(s.ConversationEventsSchema.parse({ conversation_id: "conv_8f3k2l1m", events: [event] }).events).toHaveLength(1);
  });

  it("Event envelope with typed payload", () => {
    const parsed = s.EventSchema.parse(event);
    expect(parsed.type === "policy_decision" && parsed.payload.decision.outcome).toBe("DENY");
  });

  it("rejects a policy_decision event whose payload is not a Decision", () => {
    expect(s.EventSchema.safeParse({ ...event, payload: {} }).success).toBe(false);
  });

  it("rejects malformed event ids", () => {
    expect(s.EventSchema.safeParse({ ...event, event_id: "evt_short" }).success).toBe(false);
  });

  it("every payload shape in the table", () => {
    const base = { event_id: "evt_a1b2c3d4", conversation_id: "c", seq: 0, at: "2026-11-21T12:00:00Z" };
    const payloads: Record<string, unknown> = {
      user_message: { text: "hi" },
      agent_message: { text: "hello" },
      tool_call: { call_id: "c1", tool: "get_order", args: { order_id: "ord_q1w2e3" } },
      tool_result: { call_id: "c1", ok: true, result: { status: "delivered" }, error: null, latency_ms: 120 },
      model_call: { model: "m", input_tokens: 10, output_tokens: 5, latency_ms: 900, cost_usd: 0.001 },
      action_proposed: { intent },
      policy_decision: { decision },
      approval_requested: { approval_id: "apr_5t6y7u8i", intent_id: "int_9x8y7z6w" },
      approval_resolved: { approval_id: "apr_5t6y7u8i", resolution: "approved", reviewer: "ops", note: null },
      action_executed: { intent_id: "int_9x8y7z6w", idempotency_key: "idem_123456", result: {} },
      action_failed: { intent_id: "int_9x8y7z6w", error: "timeout", retryable: true, attempt: 1 },
      follow_up_scheduled: { follow_up_id: "fu_1", due_at: "2026-11-23T12:00:00Z", note: "check" },
      follow_up_fired: { follow_up_id: "fu_1" },
      conversation_started: {},
      verification_requested: {},
      verification_completed: {},
      conversation_ended: {},
    };
    expect(Object.keys(payloads).sort()).toEqual([...s.EventTypeSchema.options].sort());
    for (const [type, payload] of Object.entries(payloads)) {
      const r = s.EventSchema.safeParse({ ...base, type, payload });
      expect(r.success, type).toBe(true);
    }
  });

  it("ActionIntent and every args variant", () => {
    expect(s.ActionIntentSchema.parse(intent).args.action).toBe("issue_refund");
    const address = { line1: "1 Fictional Way", city: "Springfield", region: "OR", postal_code: "97000", country: "US" };
    const variants = [
      { action: "issue_store_credit", customer_id: "cus_k2m9x1", amount_cents: 500, reason: "late" },
      { action: "cancel_order", order_id: "ord_q1w2e3", reason: "changed mind" },
      { action: "update_address", order_id: "ord_q1w2e3", new_address: address },
      { action: "create_ticket", subject: "Help", body: "Body" },
      { action: "escalate_to_human", reason: "angry" },
      { action: "schedule_follow_up", due_at: "2026-11-23T12:00:00Z", note: "check" },
    ];
    expect(variants.map((v) => v.action).concat("issue_refund").sort()).toEqual([...s.ActionNameSchema.options].sort());
    for (const args of variants) expect(s.ActionArgsSchema.safeParse(args).success, args.action).toBe(true);
    expect(s.ActionArgsSchema.safeParse({ action: "issue_refund", order_id: "o", amount_cents: 0, reason: "x" }).success).toBe(false);
    expect(s.ActionArgsSchema.safeParse({ action: "delete_database" }).success).toBe(false);
  });

  it("Decision", () => {
    const d = s.DecisionSchema.parse(decision);
    expect(d.rule_results[1].reason_code).toBe("OUTSIDE_RETURN_WINDOW");
    expect(s.DecisionSchema.safeParse({ ...decision, outcome: "MAYBE" }).success).toBe(false);
  });

  it("approvals", () => {
    const list = s.ApprovalListSchema.parse({
      items: [
        {
          approval_id: "apr_5t6y7u8i",
          conversation_id: "conv_8f3k2l1m",
          status: "pending",
          requested_at: "2026-11-21T12:00:04Z",
          intent,
          decision: { ...decision, outcome: "REQUIRE_APPROVAL" },
          resolved_at: null,
          reviewer: null,
          note: null,
        },
      ],
    });
    expect(list.items[0].status).toBe("pending");
    expect(s.ResolveApprovalRequestSchema.parse({ resolution: "approved", note: "Verified photo of damage" })).toBeTruthy();
    expect(s.ResolveApprovalRequestSchema.parse({ resolution: "rejected", note: "No" })).toBeTruthy();
  });

  it("policies", () => {
    expect(
      s.PolicyListSchema.parse({
        items: [{ policy_set: "larkspur-returns", version: "2026.11.21-1", rule_count: 14, updated_at: "2026-11-21T10:00:00Z" }],
      }),
    ).toBeTruthy();
    expect(
      s.PolicyDetailSchema.parse({
        policy_set: "larkspur-returns",
        version: "2026.11.21-1",
        yaml: "string",
        rules: [{ id: "REFUND_WINDOW", applies_to: ["issue_refund"], description: "string" }],
      }),
    ).toBeTruthy();
  });

  it("evals", () => {
    expect(
      s.EvalRunListSchema.parse({
        items: [
          {
            run_id: "run_20261121_1200",
            suite: "full",
            started_at: "2026-11-21T12:00:00Z",
            finished_at: "2026-11-21T12:41:00Z",
            git_sha: "a1b2c3d",
            policy_version: "2026.11.21-1",
            headline: {
              baseline: { task_success_rate: 0.71, unauthorized_action_rate: 0.12 },
              guarded: { task_success_rate: 0.83, unauthorized_action_rate: 0.0 },
            },
          },
        ],
      }),
    ).toBeTruthy();

    const metrics = {
      system: "guarded",
      scenarios: 1,
      trials_per_scenario: 4,
      task_success_rate: 0.83,
      unauthorized_action_rate: 0,
      false_refusal_rate: 0.05,
      correct_escalation_rate: 0.9,
      injection_resistance_rate: 1,
      duplicate_side_effects: 0,
      pass_hat_k: { "1": 0.83, "2": 0.74, "3": 0.69, "4": 0.66 },
      latency_ms_p50: 2100,
      latency_ms_p95: 5200,
      cost_usd_per_resolved: 0.012,
      by_category: { happy_path: 0.9 },
    };
    const report = s.EvalRunReportSchema.parse({
      run_id: "run_20261121_1200",
      suite: "full",
      started_at: "2026-11-21T12:00:00Z",
      finished_at: "2026-11-21T12:41:00Z",
      git_sha: "a1b2c3d",
      policy_version: "2026.11.21-1",
      agent_model: "configured-model",
      simulator_model: "configured-model",
      systems: [metrics, { ...metrics, system: "baseline" }],
      scenarios: [
        {
          scenario_id: "refund-in-window-basic",
          category: "happy_path",
          system: "guarded",
          trials: [
            { trial: 0, success: true, turns: 4, latency_ms_p50: 2000, latency_ms_p95: 4000, cost_usd: 0.01, conversation_id: "conv_x" },
          ],
        },
      ],
    });
    expect(report.systems[0].pass_hat_k["4"]).toBe(0.66);
    expect(report.scenarios[0].trials[0].unauthorized_actions).toEqual([]);
    expect(s.SystemMetricsSchema.safeParse({ ...metrics, task_success_rate: 1.2 }).success).toBe(false);
  });

  it("health and error envelope", () => {
    expect(s.HealthSchema.parse({ status: "ok", version: "0.1.0", policy_version: "2026.11.21-1" })).toBeTruthy();
    expect(s.ApiErrorEnvelopeSchema.parse({ error: { code: "NOT_FOUND", message: "nope" } }).error.code).toBe("NOT_FOUND");
  });
});

describe("enum drift against api.md", () => {
  const doc = readFileSync(path.resolve(import.meta.dirname, "../../docs/contracts/api.md"), "utf8");

  /** The doc lists enums as "`field` ∈ `a, b, c`" — return the second code span, split. */
  function listAfter(marker: string): string[] {
    const line = doc.split(/\r?\n/).find((l) => l.startsWith(marker));
    if (!line) throw new Error(`marker not found: ${marker}`);
    const spans = [...line.matchAll(/`([^`]+)`/g)].map((m) => m[1]);
    return spans[1].split(",").map((v) => v.trim());
  }

  it("event types match", () => {
    expect(listAfter("`type` ∈").sort()).toEqual([...s.EventTypeSchema.options].sort());
  });

  it("action names match", () => {
    expect(listAfter("`args.action` ∈").sort()).toEqual([...s.ActionNameSchema.options].sort());
  });

  it("decision outcomes match", () => {
    expect(listAfter("`outcome` ∈").sort()).toEqual([...s.DecisionOutcomeSchema.options].sort());
  });
});
