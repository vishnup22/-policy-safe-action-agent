import { ApiError, type ApiClient } from "./client";
import { ConversationBuilder, DAY, MINUTE, iso, prng } from "./mock/builder";
import { buildEvalRuns, summarizeRun } from "./mock/evals";
import { MOCK_POLICY_DETAIL, MOCK_POLICY_SUMMARY } from "./mock/policies";
import { buildSeed } from "./mock/seed";
import { DEMO_CUSTOMERS, FALLBACK_REPLY, STORIES, routeStory } from "./mock/stories";
import * as s from "./schemas";
import type {
  Approval,
  ApprovalStatus,
  ConversationSummary,
  CreateConversationRequest,
  EvalRunReport,
  Event,
  ResolveApprovalRequest,
} from "./types";
import { DEFAULT_MOCK_PASSCODE } from "./config";

export { DEFAULT_MOCK_PASSCODE };

const CHAT_EPOCH = "2026-11-21T12:00:00Z";

export interface MockClientOptions {
  /** Inclusive latency range in ms; [0, 0] disables delays (tests). */
  latencyMs?: [number, number];
  seed?: number;
  passcode?: string;
}

interface MockConversation {
  conversation_id: string;
  customer_id: string | null;
  events: Event[];
}

/**
 * In-memory implementation of the API contract. State is seeded from
 * deterministic fixtures; every response is validated against the Zod schemas
 * so the mock can never drift from docs/contracts/api.md.
 */
export class MockClient implements ApiClient {
  readonly mode = "mock" as const;
  private readonly rand: () => number;
  private readonly latency: [number, number];
  private readonly passcode: string;
  private readonly conversations = new Map<string, MockConversation>();
  private readonly approvals = new Map<string, Approval>();
  private readonly evalRuns: EvalRunReport[];
  private chatClock = Date.parse(CHAT_EPOCH);

  constructor(opts: MockClientOptions = {}) {
    this.rand = prng(opts.seed ?? 42);
    this.latency = opts.latencyMs ?? [120, 450];
    this.passcode = opts.passcode ?? DEFAULT_MOCK_PASSCODE;
    const seed = buildSeed();
    for (const c of seed.conversations) {
      this.conversations.set(c.conversation_id, {
        conversation_id: c.conversation_id,
        customer_id: c.customer_id,
        events: c.events,
      });
    }
    for (const a of seed.approvals) this.approvals.set(a.approval_id, a);
    this.evalRuns = buildEvalRuns();
  }

  private async delay(): Promise<void> {
    const [min, max] = this.latency;
    if (max <= 0) return;
    const ms = Math.round(min + this.rand() * (max - min));
    await new Promise((resolve) => setTimeout(resolve, ms));
  }

  private conversation(id: string): MockConversation {
    const c = this.conversations.get(id);
    if (!c) throw new ApiError(404, "CONVERSATION_NOT_FOUND", `Conversation ${id} not found`);
    return c;
  }

  private nextId(prefix: string): string {
    let id = "";
    while (id.length < 8) id += Math.floor(this.rand() * 36).toString(36);
    return `${prefix}_${id}`;
  }

  async login(passcode: string) {
    await this.delay();
    if (passcode !== this.passcode) {
      throw new ApiError(401, "INVALID_PASSCODE", "That passcode isn't right.");
    }
    return s.LoginResponseSchema.parse({
      token: this.nextId("mocktok"),
      expires_at: iso(Date.parse(CHAT_EPOCH) + DAY),
    });
  }

  async health() {
    await this.delay();
    return s.HealthSchema.parse({
      status: "ok",
      version: "0.1.0-mock",
      policy_version: MOCK_POLICY_SUMMARY.version,
    });
  }

  async createConversation(req: CreateConversationRequest) {
    await this.delay();
    const email = req.customer_email?.trim().toLowerCase();
    let customerId: string | null = null;
    if (email) {
      customerId =
        DEMO_CUSTOMERS.find((c) => c.email === email)?.customer_id ?? this.nextId("cus").replace("cus_", "cus_x");
    }
    const id = this.nextId("conv");
    this.chatClock += 5 * MINUTE;
    const b = new ConversationBuilder(id, iso(this.chatClock));
    b.started(customerId, iso(this.chatClock));
    this.conversations.set(id, { conversation_id: id, customer_id: customerId, events: b.events });
    return s.CreateConversationResponseSchema.parse({ conversation_id: id, started_at: b.events[0].at });
  }

  async listConversations(params: { limit?: number; cursor?: string } = {}) {
    await this.delay();
    const items = [...this.conversations.values()]
      .map(summarize)
      .sort((a, b) => b.last_event_at.localeCompare(a.last_event_at));
    const start = params.cursor ? Number(params.cursor) : 0;
    const limit = params.limit ?? 50;
    const page = items.slice(start, start + limit);
    const next = start + limit < items.length ? String(start + limit) : null;
    return s.ConversationListSchema.parse({ items: page, next_cursor: next });
  }

  async sendMessage(conversationId: string, text: string) {
    await this.delay();
    const convo = this.conversation(conversationId);
    if (convo.events.some((e) => e.type === "conversation_ended")) {
      throw new ApiError(409, "CONVERSATION_ENDED", "This conversation has ended.");
    }
    const before = convo.events.length;
    const b = new ConversationBuilder(conversationId, CHAT_EPOCH, convo.events);
    const story = routeStory(text);
    let reply: string;
    let pendingApprovalId: string | null = null;
    if (story) {
      const result = STORIES[story](b, { customerId: convo.customer_id }, text);
      reply = result.reply;
      if (result.approval) {
        this.approvals.set(result.approval.approval_id, result.approval);
        pendingApprovalId = result.approval.approval_id;
      }
    } else {
      b.user(text);
      b.model(1100, 45);
      reply = FALLBACK_REPLY;
      b.agent(reply);
    }
    this.chatClock = Math.max(this.chatClock, b.nowMs);
    const events = convo.events.slice(before);
    return s.SendMessageResponseSchema.parse({
      reply: { text: reply, at: events.at(-1)!.at },
      events,
      pending_approval_id: pendingApprovalId,
    });
  }

  async getEvents(conversationId: string) {
    await this.delay();
    const convo = this.conversation(conversationId);
    return s.ConversationEventsSchema.parse({ conversation_id: conversationId, events: convo.events });
  }

  async listApprovals(status?: ApprovalStatus) {
    await this.delay();
    const items = [...this.approvals.values()]
      .filter((a) => !status || a.status === status)
      .sort((a, b) => b.requested_at.localeCompare(a.requested_at));
    return s.ApprovalListSchema.parse({ items });
  }

  async resolveApproval(approvalId: string, req: ResolveApprovalRequest) {
    await this.delay();
    const approval = this.approvals.get(approvalId);
    if (!approval) throw new ApiError(404, "APPROVAL_NOT_FOUND", `Approval ${approvalId} not found`);
    if (approval.status !== "pending") {
      throw new ApiError(409, "APPROVAL_ALREADY_RESOLVED", `Approval was already ${approval.status}.`);
    }
    const convo = this.conversation(approval.conversation_id);
    const b = new ConversationBuilder(convo.conversation_id, CHAT_EPOCH, convo.events);
    b.advance(20 * MINUTE);
    const reviewer = "demo.operator@example.com";
    const note = req.note?.trim() ? req.note.trim() : null;
    b.push("approval_resolved", { approval_id: approvalId, resolution: req.resolution, reviewer, note }, { advanceMs: 0 });
    if (req.resolution === "approved") b.executed(approval.intent, executionResult(approval));
    const updated: Approval = {
      ...approval,
      status: req.resolution,
      resolved_at: b.events.at(-1)!.at,
      reviewer,
      note,
    };
    this.approvals.set(approvalId, updated);
    return s.ApprovalSchema.parse(updated);
  }

  async listPolicies() {
    await this.delay();
    return s.PolicyListSchema.parse({ items: [MOCK_POLICY_SUMMARY] });
  }

  async getPolicy(policySet: string) {
    await this.delay();
    if (policySet !== MOCK_POLICY_DETAIL.policy_set) {
      throw new ApiError(404, "POLICY_NOT_FOUND", `Policy set ${policySet} not found`);
    }
    return s.PolicyDetailSchema.parse(MOCK_POLICY_DETAIL);
  }

  async listEvalRuns(params: { limit?: number } = {}) {
    await this.delay();
    const items = this.evalRuns.slice(0, params.limit ?? 20).map(summarizeRun);
    return s.EvalRunListSchema.parse({ items });
  }

  async getEvalRun(runId: string) {
    await this.delay();
    const run = this.evalRuns.find((r) => r.run_id === runId);
    if (!run) throw new ApiError(404, "RUN_NOT_FOUND", `Eval run ${runId} not found`);
    return s.EvalRunReportSchema.parse(run);
  }
}

function executionResult(approval: Approval): Record<string, unknown> {
  const { args, intent_id } = approval.intent;
  const ref = intent_id.slice(4, 12);
  switch (args.action) {
    case "issue_refund":
      return { refund_id: `re_test_${ref}`, status: "succeeded", amount_cents: args.amount_cents };
    case "issue_store_credit":
      return { credit_id: `sc_test_${ref}`, amount_cents: args.amount_cents };
    default:
      return { status: "succeeded" };
  }
}

export function summarize(c: MockConversation): ConversationSummary {
  const ev = c.events;
  const requested = new Set<string>();
  const resolved = new Set<string>();
  let rejected = 0;
  for (const e of ev) {
    if (e.type === "approval_requested") requested.add(e.payload.approval_id);
    if (e.type === "approval_resolved") {
      resolved.add(e.payload.approval_id);
      if (e.payload.resolution === "rejected") rejected += 1;
    }
  }
  const awaiting = [...requested].some((id) => !resolved.has(id));
  const ended = ev.some((e) => e.type === "conversation_ended");
  return {
    conversation_id: c.conversation_id,
    started_at: ev[0].at,
    last_event_at: ev.at(-1)!.at,
    customer_id: c.customer_id,
    status: ended ? "ended" : awaiting ? "awaiting_approval" : "active",
    message_count: ev.filter((e) => e.type === "user_message" || e.type === "agent_message").length,
    actions_executed: ev.filter((e) => e.type === "action_executed").length,
    actions_blocked:
      ev.filter(
        (e) =>
          e.type === "policy_decision" &&
          (e.payload.decision.outcome === "DENY" || e.payload.decision.outcome === "REQUIRE_VERIFICATION"),
      ).length + rejected,
  };
}
