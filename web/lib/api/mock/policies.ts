import type { PolicyDetail, PolicySummary } from "../types";
import { POLICY_SET, POLICY_VERSION } from "./builder";

const RULES: PolicyDetail["rules"] = [
  { id: "IDENTITY_VERIFIED", applies_to: ["issue_refund", "issue_store_credit", "cancel_order", "update_address"], description: "Session identity must be verified for any money or order change" },
  { id: "ORDER_OWNERSHIP", applies_to: ["issue_refund", "cancel_order", "update_address", "create_ticket", "schedule_follow_up"], description: "Order must belong to the session customer" },
  { id: "REFUND_WINDOW", applies_to: ["issue_refund"], description: "Refunds only within 30 days of delivery" },
  { id: "REFUND_AMOUNT", applies_to: ["issue_refund"], description: "Refund cannot exceed the refundable amount" },
  { id: "HIGH_VALUE_REFUND", applies_to: ["issue_refund"], description: "Refunds over $200.00 require human approval" },
  { id: "NON_REFUNDABLE_ITEMS", applies_to: ["issue_refund"], description: "Final-sale items and gift cards are not refundable" },
  { id: "CANCEL_BEFORE_SHIPMENT", applies_to: ["cancel_order"], description: "Orders can be cancelled only before shipment" },
  { id: "ADDRESS_BEFORE_SHIPMENT", applies_to: ["update_address"], description: "Address changes only before shipment" },
  { id: "ADDRESS_SAME_COUNTRY", applies_to: ["update_address"], description: "Address changes must stay in the same country" },
  { id: "STORE_CREDIT_CAP", applies_to: ["issue_store_credit"], description: "Store credit over $50.00 requires approval" },
  { id: "STORE_CREDIT_ROLLING_CAP", applies_to: ["issue_store_credit"], description: "At most $150.00 store credit per customer per rolling 30 days" },
  { id: "TICKET_ALLOWED", applies_to: ["create_ticket"], description: "Tickets are always allowed" },
  { id: "ESCALATION_ALLOWED", applies_to: ["escalate_to_human"], description: "Escalations are always allowed" },
  { id: "FOLLOW_UP_ALLOWED", applies_to: ["schedule_follow_up"], description: "Follow-ups are always allowed" },
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
    "    applies_to: [issue_refund]",
    "    when: { fact: order.days_since_delivery, op: lte, value: 30 }",
    "    then: { decision: ALLOW }",
    "    else: { decision: DENY, reason: OUTSIDE_RETURN_WINDOW }",
    "  # … see policies/larkspur-returns.yaml",
  ].join("\n"),
  rules: RULES,
};
