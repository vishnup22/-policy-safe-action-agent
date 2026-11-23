import { describe, expect, it } from "vitest";
import { buildEvalRuns, summarizeRun } from "@/lib/api/mock/evals";
import {
  MOCK_POLICY_DETAIL,
  MOCK_POLICY_SUMMARY,
  MOCK_POLICY_VERSIONS,
  POLICY_VERSION_V2,
  diffMockPolicy,
} from "@/lib/api/mock/policies";
import { buildSeed } from "@/lib/api/mock/seed";
import { INJECTED_NOTE } from "@/lib/api/mock/stories";
import * as s from "@/lib/api/schemas";
import type { Event } from "@/lib/api/types";
import { extractActions } from "@/lib/events";

const seed = buildSeed();
const byStory = (story: string) => {
  const c = seed.conversations.find((x) => x.story === story);
  if (!c) throw new Error(`missing story ${story}`);
  return c;
};

function decisions(events: Event[]) {
  return events.flatMap((e) => (e.type === "policy_decision" ? [e.payload.decision] : []));
}

describe("seed conversations", () => {
  it("are deterministic", () => {
    expect(JSON.stringify(buildSeed())).toBe(JSON.stringify(seed));
  });

  it.each(seed.conversations.map((c) => [c.conversation_id, c] as const))(
    "%s validates against the contract and has gap-free seq",
    (_id, convo) => {
      const parsed = s.ConversationEventsSchema.parse({ conversation_id: convo.conversation_id, events: convo.events });
      parsed.events.forEach((e, i) => {
        expect(e.seq).toBe(i);
        expect(e.conversation_id).toBe(convo.conversation_id);
        if (i > 0) expect(Date.parse(e.at)).toBeGreaterThanOrEqual(Date.parse(parsed.events[i - 1].at));
        if (e.type === "policy_decision" || e.type === "action_executed") expect(e.policy_version).toBeTruthy();
      });
      expect(new Set(parsed.events.map((e) => e.event_id)).size).toBe(parsed.events.length);
    },
  );

  it("story 1: in-window refund is ALLOWED and executed", () => {
    const { events } = byStory("in_window");
    const [d] = decisions(events);
    expect(d.outcome).toBe("ALLOW");
    const [action] = extractActions(events);
    expect(action.executed?.payload.idempotency_key).toBe(action.intent.idempotency_key);
  });

  it("story 2: out-of-window refund is DENIED with OUTSIDE_RETURN_WINDOW and not executed", () => {
    const { events } = byStory("out_of_window");
    const [d] = decisions(events);
    expect(d.outcome).toBe("DENY");
    expect(d.rule_results.map((r) => r.reason_code)).toContain("OUTSIDE_RETURN_WINDOW");
    expect(events.some((e) => e.type === "action_executed")).toBe(false);
  });

  it("story 3: $340 refund requires approval and sits pending in the queue", () => {
    const { events, conversation_id } = byStory("high_value");
    const [d] = decisions(events);
    expect(d.outcome).toBe("REQUIRE_APPROVAL");
    const proposed = events.find((e) => e.type === "action_proposed");
    expect(proposed?.type === "action_proposed" && proposed.payload.intent.args).toMatchObject({ amount_cents: 34000 });
    const approval = seed.approvals.find((a) => a.conversation_id === conversation_id);
    expect(approval?.status).toBe("pending");
    expect(events.some((e) => e.type === "action_executed")).toBe(false);
  });

  it("story 4: prompt injection in order notes is blocked, and notes never reach the facts", () => {
    const { events } = byStory("injection");
    const toolResult = events.find((e) => e.type === "tool_result");
    expect(toolResult?.type === "tool_result" && toolResult.payload.result?.notes).toBe(INJECTED_NOTE);
    const [d] = decisions(events);
    expect(d.outcome).toBe("DENY");
    expect(JSON.stringify(d.facts_snapshot)).not.toContain("SYSTEM");
    expect(events.some((e) => e.type === "action_executed")).toBe(false);
  });

  it("story 5: follow-up is scheduled and later fired", () => {
    const { events } = byStory("follow_up");
    const scheduled = events.find((e) => e.type === "follow_up_scheduled");
    const fired = events.find((e) => e.type === "follow_up_fired");
    expect(scheduled && fired).toBeTruthy();
    if (scheduled?.type === "follow_up_scheduled" && fired?.type === "follow_up_fired") {
      expect(fired.payload.follow_up_id).toBe(scheduled.payload.follow_up_id);
      expect(Date.parse(fired.at)).toBeGreaterThanOrEqual(Date.parse(scheduled.payload.due_at));
    }
  });

  it("approvals cover every status and validate", () => {
    const list = s.ApprovalListSchema.parse({ items: seed.approvals });
    expect(new Set(list.items.map((a) => a.status))).toEqual(new Set(["pending", "approved", "rejected"]));
    for (const a of list.items) expect(a.decision.outcome).toBe("REQUIRE_APPROVAL");
  });

  it("policy fixtures validate", () => {
    expect(s.PolicyListSchema.parse({ items: [MOCK_POLICY_SUMMARY] }).items[0].rule_count).toBe(MOCK_POLICY_DETAIL.rules.length);
    expect(s.PolicyDetailSchema.parse(MOCK_POLICY_DETAIL)).toBeTruthy();
    expect(s.PolicyListSchema.parse({ items: MOCK_POLICY_VERSIONS }).items.map((p) => p.version)).toEqual([
      MOCK_POLICY_SUMMARY.version,
      POLICY_VERSION_V2,
    ]);
  });

  it("v1 → v2 differs only in REFUND_WINDOW, 30 → 14 days, like policies/larkspur-returns", () => {
    const diff = s.PolicyDiffSchema.parse(diffMockPolicy("larkspur-returns", MOCK_POLICY_SUMMARY.version, POLICY_VERSION_V2));
    expect(diff.changed.map((c) => c.id)).toEqual(["REFUND_WINDOW"]);
    expect(diff.added).toEqual([]);
    expect(diff.removed).toEqual([]);
    expect(diff.unchanged).toHaveLength(MOCK_POLICY_DETAIL.rules.length - 1);
    const [change] = diff.changed;
    expect(change.before.when).toEqual({ fact: "order.days_since_delivery", op: "lte", value: 30 });
    expect(change.after.when).toEqual({ fact: "order.days_since_delivery", op: "lte", value: 14 });
  });

  it("the policy diff is null for an unknown version or set", () => {
    expect(diffMockPolicy("larkspur-returns", "2020.01.01-1", POLICY_VERSION_V2)).toBeNull();
    expect(diffMockPolicy("other-set", MOCK_POLICY_SUMMARY.version, POLICY_VERSION_V2)).toBeNull();
  });
});

describe("eval run fixtures", () => {
  const runs = buildEvalRuns();

  it("has deterministic runs on both policy versions that validate", () => {
    expect(new Set(runs.map((r) => r.policy_version))).toEqual(new Set([MOCK_POLICY_SUMMARY.version, POLICY_VERSION_V2]));
    expect(JSON.stringify(buildEvalRuns())).toBe(JSON.stringify(runs));
    for (const r of runs) {
      s.EvalRunReportSchema.parse(r);
      s.EvalRunSummarySchema.parse(summarizeRun(r));
    }
  });

  it.each(runs.map((r) => [r.run_id, r] as const))("%s: guarded beats baseline on safety", (_id, run) => {
    const baseline = run.systems.find((m) => m.system === "baseline")!;
    const guarded = run.systems.find((m) => m.system === "guarded")!;
    expect(guarded.unauthorized_action_rate).toBe(0);
    expect(baseline.unauthorized_action_rate).toBeGreaterThan(0);
    expect(guarded.task_success_rate).toBeGreaterThan(baseline.task_success_rate);
  });

  it.each(runs.map((r) => [r.run_id, r] as const))("%s: pass^k is non-increasing in k", (_id, run) => {
    for (const m of run.systems) {
      const values = Object.keys(m.pass_hat_k)
        .map(Number)
        .sort((a, b) => a - b)
        .map((k) => m.pass_hat_k[String(k)]);
      expect(values).toHaveLength(m.trials_per_scenario);
      for (let i = 1; i < values.length; i++) expect(values[i]).toBeLessThanOrEqual(values[i - 1]);
      expect(values[0]).toBeCloseTo(m.task_success_rate, 3);
    }
  });
});
