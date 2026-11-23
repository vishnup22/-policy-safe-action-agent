import type { Approval, Event } from "../types";
import { ConversationBuilder, MINUTE, rule } from "./builder";
import {
  DEMO_PROMPTS,
  fireFollowUp,
  followUp,
  highValueRefund,
  inWindowRefund,
  injectionAttempt,
  outOfWindowRefund,
  pendingApproval,
  type StoryId,
} from "./stories";

export interface SeedConversation {
  conversation_id: string;
  customer_id: string | null;
  story: StoryId | "approved_credit" | "rejected_refund";
  title: string;
  events: Event[];
}

export interface SeedData {
  conversations: SeedConversation[];
  approvals: Approval[];
}

function prompt(story: StoryId): string {
  return DEMO_PROMPTS.find((p) => p.story === story)!.text;
}

function resolveApproval(
  b: ConversationBuilder,
  approval: Approval,
  resolution: "approved" | "rejected",
  reviewer: string,
  note: string,
  executionResult: Record<string, unknown>,
): Approval {
  const resolvedAt = b.advance(45 * MINUTE).now;
  b.push(
    "approval_resolved",
    { approval_id: approval.approval_id, resolution, reviewer, note },
    { advanceMs: 0 },
  );
  if (resolution === "approved") b.executed(approval.intent, executionResult);
  return { ...approval, status: resolution, resolved_at: resolvedAt, reviewer, note };
}

/** Builds the deterministic demo world. Pure: same output on every call. */
export function buildSeed(): SeedData {
  const conversations: SeedConversation[] = [];
  const approvals: Approval[] = [];

  // (1) In-window refund — ALLOW, executed.
  {
    const b = new ConversationBuilder("conv_8f3k2l1m", "2026-11-21T09:02:00Z");
    b.started("cus_k2m9x1", "2026-11-21T09:02:00Z");
    inWindowRefund(b, { customerId: "cus_k2m9x1" }, prompt("in_window"));
    b.user("Perfect, thank you!");
    b.model(900, 20);
    b.agent("You're welcome, Maya — enjoy the rest of your set.");
    b.ended();
    conversations.push({
      conversation_id: b.conversationId,
      customer_id: "cus_k2m9x1",
      story: "in_window",
      title: "Cracked mug — refund executed",
      events: b.events,
    });
  }

  // (2) Out-of-window refund — DENY OUTSIDE_RETURN_WINDOW.
  {
    const b = new ConversationBuilder("conv_b2n7c4x9", "2026-11-21T09:40:00Z");
    b.started("cus_t7p4q2", "2026-11-21T09:40:00Z");
    outOfWindowRefund(b, { customerId: "cus_t7p4q2" }, prompt("out_of_window"));
    b.ended();
    conversations.push({
      conversation_id: b.conversationId,
      customer_id: "cus_t7p4q2",
      story: "out_of_window",
      title: "Boots after 41 days — refund denied",
      events: b.events,
    });
  }

  // (3) $340 refund — REQUIRE_APPROVAL, pending.
  {
    const b = new ConversationBuilder("conv_l4mp9q2w", "2026-11-21T10:15:00Z");
    b.started("cus_p3n8w5", "2026-11-21T10:15:00Z");
    const { approval } = highValueRefund(b, { customerId: "cus_p3n8w5" }, prompt("high_value"));
    approvals.push(approval!);
    conversations.push({
      conversation_id: b.conversationId,
      customer_id: "cus_p3n8w5",
      story: "high_value",
      title: "$340 lamp refund — awaiting approval",
      events: b.events,
    });
  }

  // (4) Prompt injection in order notes — DENY.
  {
    const b = new ConversationBuilder("conv_h7nj3c5t", "2026-11-21T10:48:00Z");
    b.started("cus_j6r1z8", "2026-11-21T10:48:00Z");
    injectionAttempt(b, { customerId: "cus_j6r1z8" }, prompt("injection"));
    b.ended();
    conversations.push({
      conversation_id: b.conversationId,
      customer_id: "cus_j6r1z8",
      story: "injection",
      title: "Injected order notes — refund blocked",
      events: b.events,
    });
  }

  // (5) Follow-up scheduled, then fired 48h later on the simulated clock.
  {
    const b = new ConversationBuilder("conv_f0l5u6p7", "2026-11-19T11:20:00Z");
    b.started("cus_w9d2k4", "2026-11-19T11:20:00Z");
    followUp(b, { customerId: "cus_w9d2k4" }, prompt("follow_up"));
    fireFollowUp(b);
    b.ended();
    conversations.push({
      conversation_id: b.conversationId,
      customer_id: "cus_w9d2k4",
      story: "follow_up",
      title: "Stalled shipment — follow-up fired",
      events: b.events,
    });
  }

  // Resolved approvals so every queue tab has history.
  {
    const b = new ConversationBuilder("conv_cr3d1t7x", "2026-11-20T15:05:00Z");
    b.started("cus_k2m9x1", "2026-11-20T15:05:00Z");
    b.user("My last two deliveries were late. Is there anything you can do?");
    b.model(1300, 50);
    b.tool("get_customer", { customer_id: "cus_k2m9x1" }, { customer_id: "cus_k2m9x1", tier: "plus", store_credit_issued_30d_cents: 0 });
    b.model(1800, 110);
    const intent = b.propose(
      { action: "issue_store_credit", customer_id: "cus_k2m9x1", order_id: null, amount_cents: 7500, reason: "Two late deliveries" },
      "cus_k2m9x1",
      "Goodwill credit for repeated late deliveries",
    );
    const decision = b.decide(
      intent,
      [
        rule("IDENTITY_VERIFIED", "ALLOW", "Identity verified for this session"),
        rule("STORE_CREDIT_SINGLE_LIMIT", "REQUIRE_APPROVAL", "$75.00 exceeds the $50.00 credit limit without approval", "STORE_CREDIT_LIMIT"),
        rule("STORE_CREDIT_ROLLING_CAP", "ALLOW", "$75.00 keeps the 30-day total under $150.00"),
      ],
      {
        "session.identity_verified": true,
        "customer.tier": "plus",
        "customer.store_credit_issued_30d_cents": 0,
        "intent.amount_cents": 7500,
      },
    );
    const pending = pendingApproval("apr_c7d8e9f0", b, intent, decision);
    b.agent("I've requested a $75.00 store credit for you; a teammate will confirm shortly.");
    const resolved = resolveApproval(b, pending, "approved", "ops.lead@example.com", "Plus member, two documented late deliveries — goodwill approved.", {
      credit_id: "sc_test_7x2m",
      amount_cents: 7500,
    });
    b.agent("Good news — your $75.00 store credit has been approved and added to your account.");
    b.ended();
    approvals.push(resolved);
    conversations.push({
      conversation_id: b.conversationId,
      customer_id: "cus_k2m9x1",
      story: "approved_credit",
      title: "$75 goodwill credit — approved",
      events: b.events,
    });
  }

  {
    const b = new ConversationBuilder("conv_j4ck3t5r", "2026-11-20T16:30:00Z");
    b.started("cus_t7p4q2", "2026-11-20T16:30:00Z");
    b.user("The wool overcoat from order ord_w1x2y3 doesn't fit. I want my $260 back.");
    b.model(1400, 50);
    b.tool("get_order", { order_id: "ord_w1x2y3" }, { order_id: "ord_w1x2y3", status: "delivered", amount_paid_cents: 28080, days_since_delivery: 12 });
    b.model(2000, 120);
    const intent = b.propose(
      { action: "issue_refund", order_id: "ord_w1x2y3", amount_cents: 26000, item_skus: ["LG-COAT-003"], reason: "Does not fit" },
      "cus_t7p4q2",
      "Customer reports fit issue within window",
    );
    const decision = b.decide(
      intent,
      [
        rule("IDENTITY_VERIFIED", "ALLOW", "Identity verified for this session"),
        rule("ORDER_OWNERSHIP", "ALLOW", "Order belongs to the session customer"),
        rule("REFUND_WINDOW", "ALLOW", "Delivered 12 days ago; within the 30-day return window"),
        rule("REFUND_AMOUNT_LIMIT", "ALLOW", "$260.00 is within the $280.80 refundable"),
        rule("REFUND_HIGH_VALUE", "REQUIRE_APPROVAL", "$260.00 exceeds the $200.00 auto-approval limit", "HIGH_VALUE_REFUND"),
      ],
      {
        "session.identity_verified": true,
        "order.owned_by_session_customer": true,
        "order.days_since_delivery": 12,
        "order.amount_refundable_cents": 28080,
        "intent.amount_cents": 26000,
      },
    );
    const pending = pendingApproval("apr_g1h2j3k4", b, intent, decision);
    b.agent("Refunds over $200 need a teammate's approval — I've submitted it.");
    const resolved = resolveApproval(b, pending, "rejected", "ops.lead@example.com", "Return photos show heavy wear; offered exchange instead.", {});
    b.agent("A teammate reviewed the request and couldn't approve a refund because the coat shows wear. I can set up an exchange for a different size instead.");
    b.ended();
    approvals.push(resolved);
    conversations.push({
      conversation_id: b.conversationId,
      customer_id: "cus_t7p4q2",
      story: "rejected_refund",
      title: "$260 coat refund — rejected",
      events: b.events,
    });
  }

  return { conversations, approvals };
}
