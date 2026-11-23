"""G6: `verify_identity` is offered to both agents and unlocks actions in the same turn.

The real service is T6.2 (Lane H); these tests stand in a contract-faithful fake for
`psa.verification.verify_identity` so the agent wiring is tested independently.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from psa.clock import Clock
from psa.domain import EventType, SystemUnderTest, VerificationResult, VerifyIdentityArgs
from psa.llm import Step
from psa.store import EventLog
from psa.store.models import ConversationRow
from tests.agent.conftest import Shop, harness, last_tool_result, of_type, propose

pytestmark = pytest.mark.db
G, B = SystemUnderTest.GUARDED, SystemUnderTest.BASELINE
REPLY = Step(text="Done.")


def fake_verifier(shop: Shop, *, correct_postal: str = "00000"):  # type: ignore[no-untyped-def]
    calls: list[VerifyIdentityArgs] = []

    def verify(
        db: Session, conversation_id: str, args: VerifyIdentityArgs, *, clock: Clock, log: EventLog
    ) -> VerificationResult:
        calls.append(args)
        ok = args.email == f"{shop.me}@example.com" and args.postal_code == correct_postal
        if ok:
            row = db.get(ConversationRow, conversation_id)
            assert row is not None
            row.customer_id, row.identity_verified = shop.me, True
        result = VerificationResult(
            verified=ok,
            customer_id=shop.me if ok else None,
            attempts_remaining=3 if ok else 2,
            message="Verified." if ok else "That didn't match our records.",
        )
        log.append(
            conversation_id,
            EventType.VERIFICATION_COMPLETED,
            at=clock.now(),
            payload={
                **result.model_dump(mode="json", exclude={"message"}),
                "order_id": args.order_id,
            },
        )
        return result

    verify.calls = calls  # type: ignore[attr-defined]
    return verify


def verify_step(shop: Shop, oid: str, postal: str = "00000") -> Step:
    args: dict[str, Any] = {
        "order_id": oid,
        "email": f"{shop.me}@example.com",
        "postal_code": postal,
    }
    return Step(tool_calls=(("verify_identity", args),))


def test_anonymous_refund_verify_then_retry_executes_once(
    shop: Shop, monkeypatch: pytest.MonkeyPatch
) -> None:
    oid = shop.order()
    monkeypatch.setattr("psa.agent.agents.verify_identity", fake_verifier(shop))
    refund = propose("issue_refund", order_id=oid, amount_cents=500, reason="r")
    h = harness(
        shop, G, [refund, verify_step(shop, oid), refund, REPLY], customer_id=None, verified=False
    )
    turn = h.runtime.handle_user_message(h.conversation_id, "refund my order")
    kinds = [e.type for e in turn.events]
    assert EventType.VERIFICATION_REQUESTED in kinds
    assert kinds.index(EventType.VERIFICATION_COMPLETED) < kinds.index(EventType.ACTION_EXECUTED)
    assert shop.refunds(oid) == 1
    with shop.sessions() as db:
        row = db.get(ConversationRow, h.conversation_id)
        assert row is not None
        assert (row.customer_id, row.identity_verified) == (shop.me, True)


def test_wrong_postal_code_stays_unverified(shop: Shop, monkeypatch: pytest.MonkeyPatch) -> None:
    oid = shop.order()
    monkeypatch.setattr("psa.agent.agents.verify_identity", fake_verifier(shop))
    refund = propose("issue_refund", order_id=oid, amount_cents=500, reason="r")
    h = harness(
        shop,
        G,
        [verify_step(shop, oid, postal="99999"), refund, REPLY],
        customer_id=None,
        verified=False,
    )
    turn = h.runtime.handle_user_message(h.conversation_id, "refund")
    assert last_tool_result(turn.events)["result"]["status"] == "verification_required"
    assert shop.refunds(oid) == 0


@pytest.mark.parametrize("system", [G, B])
def test_both_agents_can_call_it(
    shop: Shop, system: SystemUnderTest, monkeypatch: pytest.MonkeyPatch
) -> None:
    oid = shop.order()
    verifier = fake_verifier(shop)
    monkeypatch.setattr("psa.agent.agents.verify_identity", verifier)
    h = harness(shop, system, [verify_step(shop, oid), REPLY], customer_id=None, verified=False)
    turn = h.runtime.handle_user_message(h.conversation_id, "it's me")
    assert len(verifier.calls) == 1  # type: ignore[attr-defined]
    assert of_type(turn.events, EventType.VERIFICATION_COMPLETED)


def test_stub_before_t6_2_is_a_tool_error_not_a_crash(shop: Shop) -> None:
    oid = shop.order()
    h = harness(shop, G, [verify_step(shop, oid), REPLY], customer_id=None, verified=False)
    turn = h.runtime.handle_user_message(h.conversation_id, "it's me")
    assert turn.reply_text == "Done."
    assert last_tool_result(turn.events)["error"].startswith("unavailable")
