"""Every read and write tool, exercised through the runtime against Postgres."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from psa.domain import EventType, OrderStatus, SystemUnderTest
from psa.llm import Step
from psa.store import CommerceRepo
from psa.store.models import FollowUpRow, StoreCreditRow
from psa.tools import StripeTestGateway, ToolFailure
from tests.agent.conftest import (
    Shop,
    direct,
    harness,
    last_tool_result,
    of_type,
    propose,
)
from tests.policy.helpers import NOW, address

pytestmark = pytest.mark.db
G, B = SystemUnderTest.GUARDED, SystemUnderTest.BASELINE
REPLY = Step(text="Done.")


def _run(shop: Shop, steps: list[Step], system: SystemUnderTest = G, **kw: Any) -> Any:
    h = harness(shop, system, [*steps, REPLY], **kw)
    return h, h.runtime.handle_user_message(h.conversation_id, "please")


def _read(shop: Shop, tool: str, **args: Any) -> dict[str, Any]:
    _, turn = _run(shop, [Step(tool_calls=((tool, args),))])
    payload = last_tool_result(turn.events)
    assert payload["ok"], payload
    return payload["result"]


# ------------------------------------------------------------------ read tools


def test_list_customer_orders(shop: Shop) -> None:
    oid = shop.order()
    shop.order(owner=shop.someone_else)
    orders = _read(shop, "list_customer_orders")["orders"]
    assert [o["order_id"] for o in orders] == [oid]


def test_list_orders_anonymous(shop: Shop) -> None:
    _, turn = _run(shop, [Step(tool_calls=(("list_customer_orders", {}),))], customer_id=None)
    assert last_tool_result(turn.events)["result"]["orders"] == []


def test_get_order_full_details_for_owner(shop: Shop) -> None:
    oid = shop.order(delivered_days_ago=12)
    result = _read(shop, "get_order", order_id=oid)
    assert result["belongs_to_session_customer"] is True
    assert result["days_since_delivery"] == 12
    assert result["amount_refundable_cents"] == 3200
    assert result["items"][0]["sku"] == "LG-MUG-014"
    assert "untrusted_customer_text" not in result


def test_get_order_not_found_is_a_tool_error(shop: Shop) -> None:
    _, turn = _run(shop, [Step(tool_calls=(("get_order", {"order_id": "ord_missing99"}),))])
    assert "not_found" in last_tool_result(turn.events)["error"]


def test_get_shipment_status(shop: Shop) -> None:
    oid = shop.order()
    result = _read(shop, "get_shipment_status", order_id=oid)
    assert result["order_status"] == "delivered"
    assert result["shipments"] == []


def test_get_shipment_status_missing_order(shop: Shop) -> None:
    _, turn = _run(shop, [Step(tool_calls=(("get_shipment_status", {"order_id": "ord_nope000"}),))])
    assert last_tool_result(turn.events)["ok"] is False


def test_get_customer_profile(shop: Shop) -> None:
    result = _read(shop, "get_customer_profile")
    assert result["customer"]["customer_id"] == shop.me
    assert result["identity_verified"] is True
    _, turn = _run(shop, [Step(tool_calls=(("get_customer_profile", {}),))], customer_id=None)
    assert last_tool_result(turn.events)["result"] == {"customer": None, "identity_verified": False}


def test_lookup_policy_filters_by_action(shop: Shop) -> None:
    result = _read(shop, "lookup_policy", action="cancel_order")
    ids = {r["id"] for r in result["rules"]}
    assert "CANCEL_BEFORE_SHIPMENT" in ids
    assert "REFUND_WINDOW" not in ids
    assert result["version"] == "2026.11.21-1"


def test_read_tool_rejects_unknown_arguments(shop: Shop) -> None:
    _, turn = _run(shop, [Step(tool_calls=(("get_order", {"order_id": "x", "admin": True}),))])
    assert "invalid arguments" in last_tool_result(turn.events)["error"]


# ------------------------------------------------------------------ write tools (guarded)


def test_store_credit_executes(shop: Shop) -> None:
    _run(shop, [propose("issue_store_credit", customer_id=shop.me, amount_cents=1500, reason="r")])
    with shop.sessions() as db:
        credits = db.scalars(
            select(StoreCreditRow).where(StoreCreditRow.customer_id == shop.me)
        ).all()
    assert [c.amount_cents for c in credits] == [1500]


def test_cancel_before_shipment_executes(shop: Shop) -> None:
    oid = shop.order(status=OrderStatus.PAID, delivered_days_ago=None)
    _run(shop, [propose("cancel_order", order_id=oid, reason="changed my mind")])
    with shop.sessions() as db:
        order = CommerceRepo(db).get_order(oid)
    assert order is not None
    assert order.status is OrderStatus.CANCELLED


def test_address_update_executes(shop: Shop) -> None:
    oid = shop.order(status=OrderStatus.PAID, delivered_days_ago=None)
    new = address(line1="77 New Lane").model_dump(mode="json")
    _run(shop, [propose("update_address", order_id=oid, new_address=new)])
    with shop.sessions() as db:
        order = CommerceRepo(db).get_order(oid)
    assert order is not None
    assert order.shipping_address.line1 == "77 New Lane"


def test_ticket_and_follow_up_execute(shop: Shop) -> None:
    oid = shop.order()
    due = (NOW + timedelta(hours=48)).isoformat()
    h, turn = _run(
        shop,
        [
            propose("create_ticket", order_id=oid, subject="Damaged", body="Box was crushed"),
            propose("schedule_follow_up", order_id=oid, due_at=due, note="check replacement"),
        ],
    )
    executed = of_type(turn.events, EventType.ACTION_EXECUTED)
    assert executed[0].payload["result"]["ticket_id"].startswith("tkt_")
    with shop.sessions() as db:
        follow_ups = db.scalars(
            select(FollowUpRow).where(FollowUpRow.conversation_id == h.conversation_id)
        ).all()
    assert len(follow_ups) == 1
    assert follow_ups[0].due_at == NOW + timedelta(hours=48)
    (scheduled,) = of_type(turn.events, EventType.FOLLOW_UP_SCHEDULED)
    assert scheduled.payload == {
        "follow_up_id": follow_ups[0].follow_up_id,
        "due_at": (NOW + timedelta(hours=48)).isoformat(),
        "note": "check replacement",
    }


def test_partial_refund_sets_partially_refunded(shop: Shop) -> None:
    oid = shop.order()
    _run(shop, [propose("issue_refund", order_id=oid, amount_cents=1000, reason="r")])
    with shop.sessions() as db:
        order = CommerceRepo(db).get_order(oid)
    assert order is not None
    assert order.status is OrderStatus.PARTIALLY_REFUNDED


# ------------------------------------------------------------------ write tools (baseline errors)


def test_baseline_unknown_order_fails(shop: Shop) -> None:
    _, turn = _run(shop, [direct("cancel_order", order_id="ord_nothere00", reason="r")], system=B)
    assert of_type(turn.events, EventType.ACTION_FAILED)[0].payload["error"].startswith("not_found")


def test_baseline_store_credit_unknown_customer_fails(shop: Shop) -> None:
    _, turn = _run(
        shop,
        [direct("issue_store_credit", customer_id="cus_ghost000", amount_cents=100, reason="r")],
        system=B,
    )
    assert of_type(turn.events, EventType.ACTION_FAILED)


def test_baseline_unknown_tool_is_an_error(shop: Shop) -> None:
    _, turn = _run(shop, [direct("launch_rocket")], system=B)
    assert "unknown_tool" in last_tool_result(turn.events)["error"]


def test_guarded_propose_without_args_object(shop: Shop) -> None:
    bad = Step(tool_calls=(("propose_action", {"action": "issue_refund", "args": "x"}),))
    _, turn = _run(shop, [bad])
    assert "invalid_input" in last_tool_result(turn.events)["error"]


# ------------------------------------------------------------------ Stripe test gateway (fake)


class _FakeStripeV1:
    def __init__(self, fail: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.fail = fail
        outer = self

        class _PI:
            def create(self, params: dict[str, Any], options: dict[str, Any]) -> Any:
                outer.calls.append(("payment_intents", params, options))
                return SimpleNamespace(id="pi_test_1")

        class _Refunds:
            def create(self, params: dict[str, Any], options: dict[str, Any]) -> Any:
                outer.calls.append(("refunds", params, options))
                if outer.fail is not None:
                    raise outer.fail
                return SimpleNamespace(id="re_test_1")

        self.payment_intents = _PI()
        self.refunds = _Refunds()


def _gateway(fail: Exception | None = None) -> tuple[StripeTestGateway, _FakeStripeV1]:
    gateway = StripeTestGateway("sk_test_fake")
    fake = _FakeStripeV1(fail)
    gateway._client = SimpleNamespace(v1=fake)  # type: ignore[assignment]
    return gateway, fake


def test_stripe_gateway_creates_test_payment_then_refunds_with_idempotency() -> None:
    gateway, fake = _gateway()
    receipt = gateway.refund(payment_intent_id=None, amount_cents=500, idempotency_key="idem_k")
    assert receipt.refund_id == "re_test_1"
    assert [c[0] for c in fake.calls] == ["payment_intents", "refunds"]
    assert fake.calls[0][1]["payment_method"] == "pm_card_visa"
    assert fake.calls[1][2] == {"idempotency_key": "idem_k"}
    assert fake.calls[1][1] == {"payment_intent": "pi_test_1", "amount": 500}


def test_stripe_gateway_uses_existing_payment_intent() -> None:
    gateway, fake = _gateway()
    gateway.refund(payment_intent_id="pi_existing", amount_cents=100, idempotency_key="k")
    assert [c[0] for c in fake.calls] == ["refunds"]


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        ("card", "card_declined", False),
        ("rate", "rate_limited", True),
        ("conn", "timeout", True),
    ],
)
def test_stripe_errors_map_to_tool_failures(error: str, code: str, retryable: bool) -> None:
    import stripe

    exc: Exception = {
        "card": stripe.CardError("declined", param=None, code="card_declined"),
        "rate": stripe.RateLimitError("slow down"),
        "conn": stripe.APIConnectionError("network"),
    }[error]
    gateway, _ = _gateway(fail=exc)
    with pytest.raises(ToolFailure) as info:
        gateway.refund(payment_intent_id="pi_x", amount_cents=1, idempotency_key="k")
    assert info.value.code == code
    assert info.value.retryable is retryable


def test_stripe_gateway_refuses_live_key() -> None:
    from psa.tools import LiveKeyError

    with pytest.raises(LiveKeyError):
        StripeTestGateway("sk_live_nope")
