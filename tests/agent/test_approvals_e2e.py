"""T6.1: approvals end-to-end across a restart, with policy re-checked at execution time."""

from __future__ import annotations

import pytest
from sqlalchemy import update

from psa.domain import EventType, SystemUnderTest
from psa.executor import ApprovalAlreadyResolvedError
from psa.llm import ScriptedLLM, Step
from psa.runtime.factory import build_runtime, default_registry
from psa.runtime.ports import ApprovalResolution, RuntimeConfig
from psa.store import transaction
from psa.store.models import ApprovalRow, OrderRow
from psa.tools import SimulatedStripe
from tests.agent.conftest import V1, Shop, harness, item, of_type, propose

pytestmark = pytest.mark.db
G = SystemUnderTest.GUARDED
REPLY = Step(text="Sent for review.")


def fresh_runtime(shop: Shop, clock):  # type: ignore[no-untyped-def]
    """A new process: new runtime object, new LLM client, same database."""
    return build_runtime(
        RuntimeConfig(system=G, policy_version=V1),
        sessions=shop.sessions,
        clock=clock,
        llm=ScriptedLLM.from_steps([Step(text="ok")]),
        payments=SimulatedStripe(),
        registry=default_registry(),
    )


def request_high_value_refund(shop: Shop):  # type: ignore[no-untyped-def]
    oid = shop.order(items=(item(price=30000),))
    h = harness(
        shop, G, [propose("issue_refund", order_id=oid, amount_cents=25000, reason="r"), REPLY]
    )
    turn = h.runtime.handle_user_message(h.conversation_id, "refund $250")
    assert turn.pending_approval_id is not None
    assert shop.refunds(oid) == 0
    return h, oid, turn.pending_approval_id


def test_approval_survives_restart_and_executes_exactly_once(shop: Shop) -> None:
    h, oid, approval_id = request_high_value_refund(shop)

    restarted = fresh_runtime(shop, h.clock)
    resolved = restarted.resolve_approval(
        approval_id, ApprovalResolution.APPROVED, reviewer="lead@example.com"
    )
    assert shop.refunds(oid) == 1
    assert shop.refunded_cents(oid) == 25000
    (executed,) = of_type(resolved.events, EventType.ACTION_EXECUTED)
    with shop.sessions() as db:
        row = db.get(ApprovalRow, approval_id)
        assert row is not None
        assert executed.payload["idempotency_key"] == row.intent["idempotency_key"]

    # The original process (or a double-click) can't execute it again.
    with pytest.raises(ApprovalAlreadyResolvedError):
        h.runtime.resolve_approval(approval_id, ApprovalResolution.APPROVED, reviewer="x")
    assert shop.refunds(oid) == 1


def test_approved_but_no_longer_allowed_is_not_executed(shop: Shop) -> None:
    h, oid, approval_id = request_high_value_refund(shop)
    # While it waits in the queue, another channel refunds most of the order.
    with transaction(shop.sessions) as db:
        db.execute(
            update(OrderRow).where(OrderRow.order_id == oid).values(amount_refunded_cents=29000)
        )

    resolved = fresh_runtime(shop, h.clock).resolve_approval(
        approval_id, ApprovalResolution.APPROVED, reviewer="lead@example.com"
    )
    assert "no longer meets store policy" in resolved.reply_text
    assert not of_type(resolved.events, EventType.ACTION_EXECUTED)
    (decision,) = of_type(resolved.events, EventType.POLICY_DECISION)
    assert decision.payload["decision"]["outcome"] == "DENY"
    assert shop.refunded_cents(oid) == 29000


def test_customer_hears_the_result_on_the_next_turn(shop: Shop) -> None:
    h, _, approval_id = request_high_value_refund(shop)
    fresh_runtime(shop, h.clock).resolve_approval(
        approval_id, ApprovalResolution.APPROVED, reviewer="lead@example.com"
    )
    h.llm.script = lambda *_: Step(text="All set.")
    h.runtime.handle_user_message(h.conversation_id, "any news?")
    assert "approved your request and it has been processed" in str(h.llm.calls[-1])
