import { strictest } from "@/lib/decisions";
import type {
  ActionArgs,
  ActionIntent,
  Decision,
  Event,
  EventOf,
  EventType,
  RuleResult,
} from "../types";

export const POLICY_SET = "larkspur-returns";
export const POLICY_VERSION = "2026.11.21-1";
export const MOCK_MODEL = "mock-llm";

export const SECOND = 1000;
export const MINUTE = 60 * SECOND;
export const HOUR = 60 * MINUTE;
export const DAY = 24 * HOUR;

/** Deterministic PRNG (mulberry32). Never use Math.random in fixtures. */
export function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function iso(ms: number): string {
  return new Date(ms).toISOString().replace(/\.000Z$/, "Z");
}

/**
 * Appends contract-valid events to one conversation with gap-free `seq`,
 * monotonically increasing timestamps and deterministic IDs.
 */
export class ConversationBuilder {
  readonly conversationId: string;
  readonly events: Event[];
  private clock: number;
  private readonly idPrefix: string;
  private intentCount = 0;
  private callCount = 0;

  constructor(conversationId: string, startAt: string, events: Event[] = []) {
    this.conversationId = conversationId;
    this.events = events;
    const last = events.at(-1);
    this.clock = last ? Date.parse(last.at) : Date.parse(startAt);
    this.idPrefix = conversationId.replace(/^conv_/, "").replace(/[^A-Za-z0-9]/g, "") || "conv";
    this.intentCount = events.filter((e) => e.type === "action_proposed").length;
    this.callCount = events.filter((e) => e.type === "tool_call").length;
  }

  get nowMs(): number {
    return this.clock;
  }

  get now(): string {
    return iso(this.clock);
  }

  advance(ms: number): this {
    this.clock += ms;
    return this;
  }

  push<T extends EventType>(
    type: T,
    payload: EventOf<T>["payload"],
    opts: { advanceMs?: number; policyVersion?: string | null } = {},
  ): EventOf<T> {
    this.clock += opts.advanceMs ?? 400;
    const seq = this.events.length;
    const event = {
      event_id: `evt_${this.idPrefix}${String(seq).padStart(4, "0")}`,
      conversation_id: this.conversationId,
      seq,
      type,
      at: iso(this.clock),
      policy_version: opts.policyVersion ?? null,
      payload,
    } as EventOf<T>;
    this.events.push(event);
    return event;
  }

  started(customerId: string | null, startAt?: string) {
    if (startAt) this.clock = Date.parse(startAt);
    return this.push("conversation_started", { customer_id: customerId, channel: "web" }, { advanceMs: 0 });
  }

  user(text: string) {
    return this.push("user_message", { text }, { advanceMs: 20 * SECOND });
  }

  agent(text: string) {
    return this.push("agent_message", { text }, { advanceMs: 300 });
  }

  model(inputTokens: number, outputTokens: number, latencyMs = 900) {
    return this.push(
      "model_call",
      {
        model: MOCK_MODEL,
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        latency_ms: latencyMs,
        cost_usd: Number(((inputTokens * 3 + outputTokens * 15) / 1_000_000).toFixed(6)),
      },
      { advanceMs: latencyMs },
    );
  }

  tool(tool: string, args: Record<string, unknown>, result: Record<string, unknown> | null, latencyMs = 120) {
    this.callCount += 1;
    const callId = `call_${this.idPrefix}${String(this.callCount).padStart(2, "0")}`;
    this.push("tool_call", { call_id: callId, tool, args }, { advanceMs: 50 });
    this.push(
      "tool_result",
      {
        call_id: callId,
        ok: result !== null,
        result,
        error: result === null ? "not_found" : null,
        latency_ms: latencyMs,
      },
      { advanceMs: latencyMs },
    );
    return callId;
  }

  propose(args: ActionArgs, customerId: string | null, justification: string): ActionIntent {
    this.intentCount += 1;
    const n = String(this.intentCount).padStart(2, "0");
    const intent: ActionIntent = {
      intent_id: `int_${(this.idPrefix + n).padEnd(8, "0")}`,
      conversation_id: this.conversationId,
      customer_id: customerId,
      args,
      justification,
      proposed_at: iso(this.clock + 100),
      idempotency_key: `idem_${this.idPrefix}_${args.action}_${n}`,
    };
    this.push("action_proposed", { intent }, { advanceMs: 100 });
    return intent;
  }

  decide(intent: ActionIntent, rules: RuleResult[], facts: Record<string, unknown>): Decision {
    const decision: Decision = {
      intent_id: intent.intent_id,
      outcome: strictest(rules.map((r) => r.outcome)),
      rule_results: rules,
      policy_set: POLICY_SET,
      policy_version: POLICY_VERSION,
      evaluated_at: iso(this.clock + 15),
      facts_snapshot: facts,
    };
    this.push("policy_decision", { decision }, { advanceMs: 15, policyVersion: POLICY_VERSION });
    return decision;
  }

  executed(intent: ActionIntent, result: Record<string, unknown>) {
    return this.push(
      "action_executed",
      { intent_id: intent.intent_id, idempotency_key: intent.idempotency_key, result },
      { advanceMs: 650, policyVersion: POLICY_VERSION },
    );
  }

  ended() {
    return this.push("conversation_ended", {}, { advanceMs: 2 * MINUTE });
  }
}

export function rule(
  rule_id: string,
  outcome: RuleResult["outcome"],
  message: string,
  reason_code: RuleResult["reason_code"] = null,
): RuleResult {
  return { rule_id, outcome, reason_code, message };
}
