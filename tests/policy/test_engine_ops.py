"""Operator, combinator and fail-closed semantics of the pure engine."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from psa.clock import SimulatedClock
from psa.domain import DecisionOutcome, ReasonCode
from psa.policy import FACTS, FactContext, PolicySet, ResolvedFacts, evaluate, parse_policy
from psa.policy.check import main as check_main
from psa.policy.engine import render_message
from psa.policy.facts import FactValue
from tests.policy.helpers import (
    NOW,
    V1,
    FakeSource,
    cancel,
    follow_up,
    order,
    refund,
    session,
    update_address,
)

COVER_ALL = """
  - id: COVER_ALL
    description: every action has a rule
    applies_to: [issue_refund, issue_store_credit, cancel_order, update_address,
                 create_ticket, escalate_to_human, schedule_follow_up]
    then: { decision: ALLOW }
"""


def _policy(when: str) -> PolicySet:
    return parse_policy(
        f"""
schema_version: 1
policy_set: ops-test
version: "2026.11.21-1"
rules:
{COVER_ALL}
  - id: UNDER_TEST
    description: rule under test
    applies_to: [issue_refund]
    when:
{when}
    else: {{ decision: DENY, reason: NO_APPLICABLE_RULE }}
"""
    )


def _outcome(when: str, values: dict[str, FactValue]) -> DecisionOutcome:
    facts = ResolvedFacts(values=values, missing={})
    return evaluate(refund(), _policy(when), facts, evaluated_at=NOW).outcome


A, D = DecisionOutcome.ALLOW, DecisionOutcome.DENY


@pytest.mark.parametrize(
    ("op", "value", "fact_value", "expected"),
    [
        ("eq", "30", 30, A),
        ("eq", "30", 31, D),
        ("ne", "30", 31, A),
        ("ne", "30", 30, D),
        ("lt", "30", 29, A),
        ("lt", "30", 30, D),
        ("lte", "30", 30, A),
        ("lte", "30", 31, D),
        ("gt", "30", 31, A),
        ("gt", "30", 30, D),
        ("gte", "30", 30, A),
        ("gte", "30", 29, D),
    ],
)
def test_comparison_operators(
    op: str, value: str, fact_value: int, expected: DecisionOutcome
) -> None:
    when = f"      {{ fact: order.days_since_delivery, op: {op}, value: {value} }}"
    assert _outcome(when, {"order.days_since_delivery": fact_value}) is expected


@pytest.mark.parametrize(
    ("op", "status", "expected"),
    [("in", "delivered", A), ("in", "shipped", D), ("not_in", "shipped", A), ("not_in", "paid", D)],
)
def test_membership_operators(op: str, status: str, expected: DecisionOutcome) -> None:
    values = "[delivered]" if op == "in" else "[paid, cancelled]"
    when = f"      {{ fact: order.status, op: {op}, value: {values} }}"
    assert _outcome(when, {"order.status": status}) is expected


def test_eq_does_not_confuse_bool_and_int() -> None:
    # True == 1 in Python; the engine must not treat them as equal.
    policy = _policy("      { fact: order.exists, op: eq, value: true }")
    facts = ResolvedFacts(values={"order.exists": 1}, missing={})  # wrong type smuggled in
    assert evaluate(refund(), policy, facts, evaluated_at=NOW).outcome is D


def test_ordering_on_wrong_runtime_type_fails_closed() -> None:
    policy = _policy("      { fact: order.days_since_delivery, op: lte, value: 30 }")
    facts = ResolvedFacts(values={"order.days_since_delivery": "10"}, missing={})
    decision = evaluate(refund(), policy, facts, evaluated_at=NOW)
    assert decision.outcome is D
    assert decision.reason_codes == (ReasonCode.MISSING_FACT,)


def test_ordering_on_bool_runtime_value_fails_closed() -> None:
    policy = _policy("      { fact: order.days_since_delivery, op: lte, value: 30 }")
    facts = ResolvedFacts(values={"order.days_since_delivery": True}, missing={})
    assert evaluate(refund(), policy, facts, evaluated_at=NOW).outcome is D


@pytest.mark.parametrize(("present", "expected"), [(True, A), (False, D)])
def test_exists_operator(present: bool, expected: DecisionOutcome) -> None:
    when = "      { fact: order.days_since_delivery, op: exists, value: true }"
    values: dict[str, FactValue] = {"order.days_since_delivery": 3} if present else {}
    assert _outcome(when, values) is expected


def test_any_and_not_combinators() -> None:
    when = """      any:
        - { fact: session.identity_verified, op: eq, value: true }
        - not: { fact: order.status, op: eq, value: delivered }"""
    assert _outcome(when, {"session.identity_verified": True}) is A  # short-circuits
    assert _outcome(when, {"session.identity_verified": False, "order.status": "paid"}) is A
    assert _outcome(when, {"session.identity_verified": False, "order.status": "delivered"}) is D


def test_value_from_compares_two_facts() -> None:
    when = "      { fact: intent.amount_cents, op: lte, value_from: order.amount_refundable_cents }"
    ok: dict[str, FactValue] = {"intent.amount_cents": 100, "order.amount_refundable_cents": 100}
    bad: dict[str, FactValue] = {"intent.amount_cents": 101, "order.amount_refundable_cents": 100}
    assert _outcome(when, ok) is A
    assert _outcome(when, bad) is D


def test_missing_fact_recorded_in_snapshot_with_reason() -> None:
    policy = _policy("      { fact: order.days_since_delivery, op: lte, value: 30 }")
    facts = ResolvedFacts(values={}, missing={"order.days_since_delivery": "not delivered"})
    decision = evaluate(refund(), policy, facts, evaluated_at=NOW)
    assert decision.facts_snapshot["_missing"] == {"order.days_since_delivery": "not delivered"}


def test_render_message_only_substitutes_known_placeholders() -> None:
    values: dict[str, FactValue] = {"order.status": "shipped"}
    assert render_message("Order is {order.status}.", values) == "Order is shipped."
    assert render_message("{order.days_since_delivery} days", values) == "unknown days"
    # No attribute access, indexing or format specs: braces that aren't fact names stay literal.
    assert render_message("{0} {__class__} {order.status!r}", values) == (
        "{0} {__class__} {order.status!r}"
    )


# ------------------------------------------------------------------ fact resolvers


def _ctx(intent_: object, *orders: object) -> FactContext:
    return FactContext(
        intent=intent_,  # type: ignore[arg-type]
        session=session(),
        source=FakeSource.with_(*orders),  # type: ignore[arg-type]
        clock=SimulatedClock(NOW),
    )


def test_follow_up_hours_ahead() -> None:
    ctx = _ctx(follow_up(hours=72))
    assert FACTS["intent.follow_up_hours_ahead"].resolve(ctx) == 72


def test_address_country_changed() -> None:
    o = order()
    assert FACTS["intent.address_country_changed"].resolve(_ctx(update_address("CA"), o)) is True
    assert FACTS["intent.address_country_changed"].resolve(_ctx(update_address("US"), o)) is False


def test_items_in_order() -> None:
    o = order()
    ok = refund(skus=("LG-MUG-014",))
    bad = refund(skus=("LG-NOPE-000",))
    assert FACTS["intent.items_in_order"].resolve(_ctx(ok, o)) is True
    assert FACTS["intent.items_in_order"].resolve(_ctx(bad, o)) is False


def test_facts_requiring_an_amount_or_items_are_missing_for_other_actions() -> None:
    o = order()
    for name in ("intent.amount_cents", "intent.items_in_order", "intent.follow_up_hours_ahead"):
        result = FACTS[name].resolve(_ctx(cancel(), o))
        assert not isinstance(result, bool | int | str), name
    assert not isinstance(FACTS["intent.address_country_changed"].resolve(_ctx(cancel(), o)), bool)


def test_customer_facts_missing_without_session_customer() -> None:
    ctx = FactContext(
        intent=refund(),
        session=session(customer_id=None, verified=False),
        source=FakeSource.with_(),
        clock=SimulatedClock(NOW),
    )
    assert not isinstance(FACTS["customer.tier"].resolve(ctx), str)
    assert not isinstance(FACTS["customer.store_credit_30d_cents"].resolve(ctx), int)


def test_order_lookups_are_cached_within_one_evaluation() -> None:
    calls: list[str] = []
    source = FakeSource.with_(order())
    original = source.get_order

    def counting(order_id: str):  # type: ignore[no-untyped-def]
        calls.append(order_id)
        return original(order_id)

    source.get_order = counting  # type: ignore[method-assign]
    from psa.policy import decide

    decide(refund(), V1, session=session(), source=source, clock=SimulatedClock(NOW))
    assert len(calls) == 1


def test_one_consistent_now_per_evaluation() -> None:
    clock = SimulatedClock(NOW)
    ctx = FactContext(intent=refund(), session=session(), source=FakeSource.with_(), clock=clock)
    first = ctx.now
    clock.advance(timedelta(days=5))
    assert ctx.now == first


# ------------------------------------------------------------------ CLI


def test_check_cli_ok(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).resolve().parents[2] / "policies"
    assert check_main([str(root)]) == 0
    out = capsys.readouterr().out
    assert "larkspur-returns@2026.11.21-1" in out
    assert out.strip().endswith("OK")


def test_check_cli_reports_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad-set" / "2026.11.21-1.yaml"
    bad.parent.mkdir()
    bad.write_text("rules: [", encoding="utf-8")
    assert check_main([str(tmp_path)]) == 1
    assert "Policy validation FAILED" in capsys.readouterr().err
