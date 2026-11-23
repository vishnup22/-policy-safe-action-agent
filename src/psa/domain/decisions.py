"""Policy decisions returned by the policy engine."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DecisionOutcome(StrEnum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_VERIFICATION = "REQUIRE_VERIFICATION"
    DENY = "DENY"


OUTCOME_PRECEDENCE: dict[DecisionOutcome, int] = {
    DecisionOutcome.ALLOW: 0,
    DecisionOutcome.REQUIRE_APPROVAL: 1,
    DecisionOutcome.REQUIRE_VERIFICATION: 2,
    DecisionOutcome.DENY: 3,
}
"""Higher wins: DENY > REQUIRE_VERIFICATION > REQUIRE_APPROVAL > ALLOW."""


def strictest(outcomes: list[DecisionOutcome]) -> DecisionOutcome:
    """Combine rule outcomes. No outcomes (no applicable rules) fails closed to DENY."""
    if not outcomes:
        return DecisionOutcome.DENY
    return max(outcomes, key=OUTCOME_PRECEDENCE.__getitem__)


class ReasonCode(StrEnum):
    # Window / timing
    OUTSIDE_RETURN_WINDOW = "OUTSIDE_RETURN_WINDOW"
    ORDER_NOT_DELIVERED = "ORDER_NOT_DELIVERED"
    ORDER_ALREADY_SHIPPED = "ORDER_ALREADY_SHIPPED"
    ORDER_ALREADY_CANCELLED = "ORDER_ALREADY_CANCELLED"
    # Money
    AMOUNT_EXCEEDS_REFUNDABLE = "AMOUNT_EXCEEDS_REFUNDABLE"
    HIGH_VALUE_REFUND = "HIGH_VALUE_REFUND"
    STORE_CREDIT_LIMIT = "STORE_CREDIT_LIMIT"
    FINAL_SALE_ITEM = "FINAL_SALE_ITEM"
    GIFT_CARD_NOT_REFUNDABLE = "GIFT_CARD_NOT_REFUNDABLE"
    ITEM_NOT_IN_ORDER = "ITEM_NOT_IN_ORDER"
    # Scheduling
    FOLLOW_UP_OUT_OF_RANGE = "FOLLOW_UP_OUT_OF_RANGE"
    # Identity / authorization
    IDENTITY_NOT_VERIFIED = "IDENTITY_NOT_VERIFIED"
    ORDER_NOT_OWNED_BY_CUSTOMER = "ORDER_NOT_OWNED_BY_CUSTOMER"
    # Integrity / fail-closed
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    MISSING_FACT = "MISSING_FACT"
    NO_APPLICABLE_RULE = "NO_APPLICABLE_RULE"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    # Address
    ADDRESS_CHANGE_AFTER_SHIPMENT = "ADDRESS_CHANGE_AFTER_SHIPMENT"
    ADDRESS_COUNTRY_CHANGE = "ADDRESS_COUNTRY_CHANGE"


class RuleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    outcome: DecisionOutcome
    reason_code: ReasonCode | None = None
    message: str = Field(description="Human-readable explanation, safe to show the customer")


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: str
    outcome: DecisionOutcome
    rule_results: tuple[RuleResult, ...]
    policy_set: str
    policy_version: str
    evaluated_at: datetime
    facts_snapshot: dict[str, Any] = Field(
        description="Exact facts used for this decision, for audit and replay"
    )

    @property
    def reason_codes(self) -> tuple[ReasonCode, ...]:
        return tuple(r.reason_code for r in self.rule_results if r.reason_code is not None)

    @property
    def deciding_rules(self) -> tuple[RuleResult, ...]:
        """Rules whose outcome equals the final outcome (what the UI should highlight)."""
        return tuple(r for r in self.rule_results if r.outcome == self.outcome)
