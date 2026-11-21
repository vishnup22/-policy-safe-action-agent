from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from psa.domain import (
    ActionArgs,
    ActionIntent,
    ActionName,
    Address,
    DecisionOutcome,
    IssueRefundArgs,
    ItemCategory,
    Order,
    OrderItem,
    OrderStatus,
    strictest,
)

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
ADDR = Address(
    line1="1 Test Way", city="Springfield", region="IL", postal_code="62701", country="US"
)


def _order(**overrides: object) -> Order:
    base: dict[str, object] = {
        "order_id": "ord_abc123",
        "customer_id": "cus_abc123",
        "status": OrderStatus.DELIVERED,
        "items": (
            OrderItem(
                sku="LG-TEE-001",
                name="Cotton Tee",
                category=ItemCategory.APPAREL,
                quantity=2,
                unit_price_cents=2500,
            ),
        ),
        "amount_paid_cents": 5400,
        "shipping_address": ADDR,
        "placed_at": NOW,
    }
    base.update(overrides)
    return Order.model_validate(base)


def test_refundable_amount() -> None:
    order = _order(amount_refunded_cents=1400)
    assert order.subtotal_cents == 5000
    assert order.amount_refundable_cents == 4000


def test_refunded_cannot_exceed_paid() -> None:
    with pytest.raises(ValidationError):
        _order(amount_refunded_cents=9999)


def test_action_args_discriminated_union() -> None:
    adapter: TypeAdapter[ActionArgs] = TypeAdapter(ActionArgs)
    parsed = adapter.validate_python(
        {"action": "issue_refund", "order_id": "ord_abc123", "amount_cents": 100, "reason": "x"}
    )
    assert isinstance(parsed, IssueRefundArgs)


def test_action_args_reject_unknown_fields() -> None:
    adapter: TypeAdapter[ActionArgs] = TypeAdapter(ActionArgs)
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "action": "issue_refund",
                "order_id": "ord_abc123",
                "amount_cents": 100,
                "reason": "x",
                "override_policy": True,
            }
        )


def test_intent_roundtrip_json() -> None:
    intent = ActionIntent(
        intent_id="int_abcdefgh",
        conversation_id="conv_1",
        args=IssueRefundArgs(order_id="ord_abc123", amount_cents=500, reason="damaged"),
        justification="Customer reports damaged item",
        proposed_at=NOW,
        idempotency_key="idem_12345678",
    )
    assert intent.action is ActionName.ISSUE_REFUND
    assert ActionIntent.model_validate_json(intent.model_dump_json()) == intent


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        ([], DecisionOutcome.DENY),
        ([DecisionOutcome.ALLOW], DecisionOutcome.ALLOW),
        (
            [DecisionOutcome.ALLOW, DecisionOutcome.REQUIRE_APPROVAL],
            DecisionOutcome.REQUIRE_APPROVAL,
        ),
        (
            [DecisionOutcome.REQUIRE_APPROVAL, DecisionOutcome.REQUIRE_VERIFICATION],
            DecisionOutcome.REQUIRE_VERIFICATION,
        ),
        ([DecisionOutcome.REQUIRE_VERIFICATION, DecisionOutcome.DENY], DecisionOutcome.DENY),
    ],
)
def test_strictest_precedence(outcomes: list[DecisionOutcome], expected: DecisionOutcome) -> None:
    assert strictest(outcomes) is expected
