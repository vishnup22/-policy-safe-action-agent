import type { ActionName, PolicyDetail, PolicyDiff, PolicySummary } from "../types";
import { POLICY_SET, POLICY_VERSION } from "./builder";

/** v2 of policies/larkspur-returns: identical to v1 except REFUND_WINDOW (30 → 14 days). */
export const POLICY_VERSION_V2 = "2026.11.21-2";

type RuleBody = Record<string, unknown> & { id: string; description: string; applies_to: ActionName[] };

const cond = (fact: string, op: string, value: unknown) => ({ fact, op, value });
const deny = (reason: string, message: string) => ({ decision: "DENY", reason, message });
const ORDER_EXISTS = cond("order.exists", "eq", true);
const HAS_ORDER = cond("intent.has_order", "eq", true);
const ITEMS_IN_ORDER = cond("intent.items_in_order", "eq", true);
const REFUNDABLE_STATUS = cond("order.status", "in", ["delivered", "partially_refunded"]);

/** The rules of policies/larkspur-returns/2026.11.21-1.yaml, as the API's diff returns them. */
const RULES_V1: RuleBody[] = [
  {
    id: "IDENTITY_VERIFIED",
    description: "Money movements and order changes require a verified identity",
    applies_to: ["issue_refund", "issue_store_credit", "cancel_order", "update_address"],
    when: cond("session.identity_verified", "eq", true),
    else: {
      decision: "REQUIRE_VERIFICATION",
      reason: "IDENTITY_NOT_VERIFIED",
      message: "Please verify your identity before I can make changes to your account.",
    },
  },
  {
    id: "ORDER_EXISTS",
    description: "The referenced order must exist",
    applies_to: ["issue_refund", "cancel_order", "update_address"],
    when: ORDER_EXISTS,
    else: deny("ORDER_NOT_FOUND", "I couldn't find that order."),
  },
  {
    id: "OPTIONAL_ORDER_EXISTS",
    description: "If an order is referenced, it must exist",
    applies_to: ["issue_store_credit", "create_ticket", "schedule_follow_up"],
    only_if: HAS_ORDER,
    when: ORDER_EXISTS,
    else: deny("ORDER_NOT_FOUND", "I couldn't find that order."),
  },
  {
    id: "ORDER_OWNERSHIP",
    description: "Customers can only change or get money back on their own orders",
    applies_to: ["issue_refund", "issue_store_credit", "cancel_order", "update_address"],
    only_if: { all: [HAS_ORDER, ORDER_EXISTS, cond("session.has_customer", "eq", true)] },
    when: cond("order.owned_by_session_customer", "eq", true),
    else: deny("ORDER_NOT_OWNED_BY_CUSTOMER", "That order isn't associated with your account."),
  },
  {
    id: "REFERENCED_ORDER_OWNERSHIP",
    description: "Tickets and follow-ups can only reference the customer's own orders",
    applies_to: ["create_ticket", "schedule_follow_up"],
    only_if: { all: [HAS_ORDER, ORDER_EXISTS] },
    when: cond("order.owned_by_session_customer", "eq", true),
    else: deny("ORDER_NOT_OWNED_BY_CUSTOMER", "That order isn't associated with your account."),
  },
  {
    id: "REFUND_REQUIRES_DELIVERY",
    description: "Refunds are only for delivered orders",
    applies_to: ["issue_refund"],
    only_if: ORDER_EXISTS,
    when: REFUNDABLE_STATUS,
    else: deny("ORDER_NOT_DELIVERED", "Refunds are available once an order is delivered; this order is {order.status}."),
  },
  {
    id: "REFUND_WINDOW",
    description: "Refunds within 30 days of delivery",
    applies_to: ["issue_refund"],
    only_if: { all: [ORDER_EXISTS, REFUNDABLE_STATUS] },
    when: cond("order.days_since_delivery", "lte", 30),
    else: deny(
      "OUTSIDE_RETURN_WINDOW",
      "This order was delivered {order.days_since_delivery} days ago; the return window is 30 days.",
    ),
  },
  {
    id: "REFUND_AMOUNT_LIMIT",
    description: "A refund cannot exceed the amount still refundable on the order",
    applies_to: ["issue_refund"],
    only_if: ORDER_EXISTS,
    when: { fact: "intent.amount_cents", op: "lte", value_from: "order.amount_refundable_cents" },
    else: deny(
      "AMOUNT_EXCEEDS_REFUNDABLE",
      "The requested amount is more than the {order.amount_refundable_cents} cents still refundable on this order.",
    ),
  },
  {
    id: "REFUND_ITEMS_IN_ORDER",
    description: "Every item named in a refund must belong to the order",
    applies_to: ["issue_refund"],
    only_if: ORDER_EXISTS,
    when: ITEMS_IN_ORDER,
    else: deny("ITEM_NOT_IN_ORDER", "One or more of those items isn't part of this order."),
  },
  {
    id: "REFUND_FINAL_SALE",
    description: "Final-sale items are not refundable",
    applies_to: ["issue_refund"],
    only_if: { all: [ORDER_EXISTS, ITEMS_IN_ORDER] },
    when: cond("intent.includes_final_sale", "eq", false),
    else: deny("FINAL_SALE_ITEM", "Final-sale items can't be refunded."),
  },
  {
    id: "REFUND_GIFT_CARD",
    description: "Gift cards are not refundable",
    applies_to: ["issue_refund"],
    only_if: { all: [ORDER_EXISTS, ITEMS_IN_ORDER] },
    when: cond("intent.includes_gift_card", "eq", false),
    else: deny("GIFT_CARD_NOT_REFUNDABLE", "Gift cards can't be refunded."),
  },
  {
    id: "REFUND_HIGH_VALUE",
    description: "Refunds over $200.00 need human approval",
    applies_to: ["issue_refund"],
    when: cond("intent.amount_cents", "gt", 20000),
    then: {
      decision: "REQUIRE_APPROVAL",
      reason: "HIGH_VALUE_REFUND",
      message: "Refunds over $200 are reviewed by a team member; I've sent this for approval.",
    },
  },
  {
    id: "STORE_CREDIT_OWN_ACCOUNT",
    description: "Store credit can only be issued to the session customer's own account",
    applies_to: ["issue_store_credit"],
    only_if: cond("session.has_customer", "eq", true),
    when: cond("intent.targets_session_customer", "eq", true),
    else: deny("ORDER_NOT_OWNED_BY_CUSTOMER", "Store credit can only be added to your own account."),
  },
  {
    id: "STORE_CREDIT_SINGLE_LIMIT",
    description: "Store credit over $50.00 needs human approval",
    applies_to: ["issue_store_credit"],
    when: cond("intent.amount_cents", "gt", 5000),
    then: {
      decision: "REQUIRE_APPROVAL",
      reason: "STORE_CREDIT_LIMIT",
      message: "Store credit over $50 is reviewed by a team member; I've sent this for approval.",
    },
  },
  {
    id: "STORE_CREDIT_ROLLING_CAP",
    description: "At most $150.00 of store credit per customer in any 30 days",
    applies_to: ["issue_store_credit"],
    when: cond("customer.store_credit_30d_after_intent_cents", "lte", 15000),
    else: deny("STORE_CREDIT_LIMIT", "This would exceed the $150 store-credit limit for a 30-day period."),
  },
  {
    id: "NOT_ALREADY_CLOSED",
    description: "Cancelled or fully refunded orders can't be changed",
    applies_to: ["cancel_order", "update_address"],
    only_if: ORDER_EXISTS,
    when: cond("order.status", "not_in", ["cancelled", "refunded"]),
    else: deny("ORDER_ALREADY_CANCELLED", "This order is already {order.status}."),
  },
  {
    id: "CANCEL_BEFORE_SHIPMENT",
    description: "Orders can only be cancelled before they ship",
    applies_to: ["cancel_order"],
    only_if: ORDER_EXISTS,
    when: cond("order.is_shipped", "eq", false),
    else: deny(
      "ORDER_ALREADY_SHIPPED",
      "This order has already shipped, so it can't be cancelled; you can return it once it arrives.",
    ),
  },
  {
    id: "ADDRESS_BEFORE_SHIPMENT",
    description: "Shipping address can only change before the order ships",
    applies_to: ["update_address"],
    only_if: ORDER_EXISTS,
    when: cond("order.is_shipped", "eq", false),
    else: deny("ADDRESS_CHANGE_AFTER_SHIPMENT", "This order has already shipped, so its address can't be changed."),
  },
  {
    id: "ADDRESS_SAME_COUNTRY",
    description: "Address changes must stay within the original country",
    applies_to: ["update_address"],
    only_if: ORDER_EXISTS,
    when: cond("intent.address_country_changed", "eq", false),
    else: deny("ADDRESS_COUNTRY_CHANGE", "Shipping addresses can't be moved to a different country."),
  },
  {
    id: "TICKET_ALLOWED",
    description: "Customers can always open a support ticket",
    applies_to: ["create_ticket"],
    then: { decision: "ALLOW", message: "Support ticket allowed." },
  },
  {
    id: "ESCALATION_ALLOWED",
    description: "Customers can always reach a human",
    applies_to: ["escalate_to_human"],
    then: { decision: "ALLOW", message: "Escalation to a human is always allowed." },
  },
  {
    id: "FOLLOW_UP_WINDOW",
    description: "Follow-ups must be scheduled between 1 hour and 14 days ahead",
    applies_to: ["schedule_follow_up"],
    when: {
      all: [cond("intent.follow_up_hours_ahead", "gte", 1), cond("intent.follow_up_hours_ahead", "lte", 336)],
    },
    else: deny("FOLLOW_UP_OUT_OF_RANGE", "I can schedule a follow-up between 1 hour and 14 days from now."),
  },
];

const RULES_V2: RuleBody[] = RULES_V1.map((rule) =>
  rule.id === "REFUND_WINDOW"
    ? {
        ...rule,
        description: "Refunds within 14 days of delivery",
        when: cond("order.days_since_delivery", "lte", 14),
        else: deny(
          "OUTSIDE_RETURN_WINDOW",
          "This order was delivered {order.days_since_delivery} days ago; the return window is 14 days.",
        ),
      }
    : rule,
);

const RULES_BY_VERSION: Record<string, RuleBody[]> = {
  [POLICY_VERSION]: RULES_V1,
  [POLICY_VERSION_V2]: RULES_V2,
};

export const MOCK_POLICY_SUMMARY: PolicySummary = {
  policy_set: POLICY_SET,
  version: POLICY_VERSION,
  rule_count: RULES_V1.length,
  updated_at: "2026-11-21T10:00:00Z",
};

/** Every version of every policy set, as `GET /api/policies` lists them. */
export const MOCK_POLICY_VERSIONS: PolicySummary[] = [
  MOCK_POLICY_SUMMARY,
  { policy_set: POLICY_SET, version: POLICY_VERSION_V2, rule_count: RULES_V2.length, updated_at: "2026-11-21T10:05:00Z" },
];

/** The active version (the runtime's configured `policy_version`). */
export const MOCK_POLICY_DETAIL: PolicyDetail = {
  policy_set: POLICY_SET,
  version: POLICY_VERSION,
  yaml: [
    `policy_set: ${POLICY_SET}`,
    `version: "${POLICY_VERSION}"`,
    "rules:",
    "  - id: REFUND_WINDOW",
    "    description: Refunds within 30 days of delivery",
    "    applies_to: [issue_refund]",
    "    when: { fact: order.days_since_delivery, op: lte, value: 30 }",
    "    else:",
    "      decision: DENY",
    "      reason: OUTSIDE_RETURN_WINDOW",
    "",
    "  - id: REFUND_ITEMS_IN_ORDER",
    "    description: Every item named in a refund must belong to the order",
    "    applies_to: [issue_refund]",
    "    when: { fact: intent.items_in_order, op: eq, value: true }",
    "    else:",
    "      decision: DENY",
    "      reason: ITEM_NOT_IN_ORDER",
    "",
    "  - id: REFUND_HIGH_VALUE",
    "    description: Refunds over $200.00 need human approval",
    "    applies_to: [issue_refund]",
    "    when: { fact: intent.amount_cents, op: gt, value: 20000 }",
    "    then:",
    "      decision: REQUIRE_APPROVAL",
    "      reason: HIGH_VALUE_REFUND",
    "  # … see policies/larkspur-returns/",
  ].join("\n"),
  rules: RULES_V1.map(({ id, applies_to, description }) => ({ id, applies_to, description })),
};

function sameRule(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Rule-level diff, computed the way `GET /api/policies/{set}/diff` does; `null` for an unknown version. */
export function diffMockPolicy(policySet: string, from: string, to: string): PolicyDiff | null {
  const before = RULES_BY_VERSION[from];
  const after = RULES_BY_VERSION[to];
  if (policySet !== POLICY_SET || !before || !after) return null;
  const beforeById = new Map(before.map((r) => [r.id, r]));
  const afterIds = new Set(after.map((r) => r.id));
  const diff: PolicyDiff = { policy_set: policySet, from_version: from, to_version: to, added: [], removed: [], changed: [], unchanged: [] };
  for (const rule of after) {
    const old = beforeById.get(rule.id);
    if (!old) diff.added.push({ id: rule.id, rule });
    else if (sameRule(old, rule)) diff.unchanged.push(rule.id);
    else diff.changed.push({ id: rule.id, before: old, after: rule });
  }
  for (const rule of before) if (!afterIds.has(rule.id)) diff.removed.push({ id: rule.id, rule });
  return diff;
}
