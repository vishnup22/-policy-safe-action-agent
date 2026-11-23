import type { PolicyDetail, PolicySummary } from "../types";
import { POLICY_SET, POLICY_VERSION } from "./builder";

const RULES: PolicyDetail["rules"] = [
  { id: "IDENTITY_VERIFIED", applies_to: ["issue_refund", "issue_store_credit", "cancel_order", "update_address"], description: "Session identity must be verified for any money or order change" },
  { id: "ORDER_OWNERSHIP", applies_to: ["issue_refund", "cancel_order", "update_address", "create_ticket", "schedule_follow_up"], description: "Order must belong to the session customer" },
  { id: "REFUND_WINDOW", applies_to: ["issue_refund"], description: "Refunds within 30 days of delivery" },
  { id: "REFUND_AMOUNT_LIMIT", applies_to: ["issue_refund"], description: "Refund cannot exceed the refundable amount" },
  { id: "REFUND_ITEMS_IN_ORDER", applies_to: ["issue_refund"], description: "Every item named in a refund must belong to the order" },
  { id: "REFUND_FINAL_SALE", applies_to: ["issue_refund"], description: "Final-sale items are not refundable" },
  { id: "REFUND_GIFT_CARD", applies_to: ["issue_refund"], description: "Gift cards are not refundable" },
  { id: "REFUND_HIGH_VALUE", applies_to: ["issue_refund"], description: "Refunds over $200.00 require human approval" },
  { id: "CANCEL_BEFORE_SHIPMENT", applies_to: ["cancel_order"], description: "Orders can be cancelled only before shipment" },
  { id: "ADDRESS_BEFORE_SHIPMENT", applies_to: ["update_address"], description: "Address changes only before shipment" },
  { id: "ADDRESS_SAME_COUNTRY", applies_to: ["update_address"], description: "Address changes must stay in the same country" },
  { id: "STORE_CREDIT_SINGLE_LIMIT", applies_to: ["issue_store_credit"], description: "Store credit over $50.00 requires approval" },
  { id: "STORE_CREDIT_ROLLING_CAP", applies_to: ["issue_store_credit"], description: "At most $150.00 store credit per customer per rolling 30 days" },
  { id: "TICKET_ALLOWED", applies_to: ["create_ticket"], description: "Tickets are always allowed" },
  { id: "ESCALATION_ALLOWED", applies_to: ["escalate_to_human"], description: "Escalations are always allowed" },
  { id: "FOLLOW_UP_WINDOW", applies_to: ["schedule_follow_up"], description: "Follow-ups must be scheduled between 1 hour and 14 days ahead" },
];

export const MOCK_POLICY_SUMMARY: PolicySummary = {
  policy_set: POLICY_SET,
  version: POLICY_VERSION,
  rule_count: RULES.length,
  updated_at: "2026-11-21T10:00:00Z",
};

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
    "    description: Refunds over $200.00 require human approval",
    "    applies_to: [issue_refund]",
    "    when: { fact: intent.amount_cents, op: gt, value: 20000 }",
    "    then:",
    "      decision: REQUIRE_APPROVAL",
    "      reason: HIGH_VALUE_REFUND",
    "  # … see policies/larkspur-returns/",
  ].join("\n"),
  rules: RULES,
};
