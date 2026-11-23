"""Property-based tests on the pure engine: random facts, invariant outcomes."""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from psa.domain import OUTCOME_PRECEDENCE, ActionName, DecisionOutcome
from psa.policy import FACTS, FactType, PolicySet, ResolvedFacts, evaluate, required_facts
from psa.policy.facts import FactValue
from psa.policy.schema import Rule
from tests.policy.helpers import NOW, V1, V2, cancel, escalate, refund, store_credit, update_address

INTENTS = {
    ActionName.ISSUE_REFUND: refund(),
    ActionName.ISSUE_STORE_CREDIT: store_credit(),
    ActionName.CANCEL_ORDER: cancel(),
    ActionName.UPDATE_ADDRESS: update_address(),
    ActionName.ESCALATE_TO_HUMAN: escalate(),
}


def _value_strategy(name: str) -> st.SearchStrategy[FactValue]:
    spec = FACTS[name]
    if spec.allowed_values is not None:
        return st.sampled_from(sorted(spec.allowed_values))
    if spec.type is FactType.BOOL:
        return st.booleans()
    if spec.type is FactType.INT:
        return st.integers(min_value=-10, max_value=100_000)
    return st.text(max_size=10)


@st.composite
def scenario(draw: st.DrawFn) -> tuple[PolicySet, ActionName, ResolvedFacts]:
    policy = draw(st.sampled_from([V1, V2]))
    action = draw(st.sampled_from(sorted(INTENTS)))
    names = sorted(required_facts(policy, INTENTS[action]))
    values: dict[str, FactValue] = {}
    missing: dict[str, str] = {}
    for name in names:
        if draw(st.integers(0, 9)) == 0:  # ~10% of facts unavailable
            missing[name] = "dropped by test"
        else:
            values[name] = draw(_value_strategy(name))
    return policy, action, ResolvedFacts(values=values, missing=missing)


@settings(max_examples=300, deadline=None)
@given(scenario())
def test_evaluation_is_deterministic(case: tuple[PolicySet, ActionName, ResolvedFacts]) -> None:
    policy, action, facts = case
    first = evaluate(INTENTS[action], policy, facts, evaluated_at=NOW)
    second = evaluate(INTENTS[action], policy, facts, evaluated_at=NOW)
    assert first == second


@settings(max_examples=300, deadline=None)
@given(scenario(), st.data())
def test_dropping_any_fact_that_was_read_never_allows(
    case: tuple[PolicySet, ActionName, ResolvedFacts], data: st.DataObject
) -> None:
    policy, action, facts = case
    decision = evaluate(INTENTS[action], policy, facts, evaluated_at=NOW)
    read = sorted(k for k in decision.facts_snapshot if not k.startswith("_"))
    if not read:
        return
    victim = data.draw(st.sampled_from(read))
    values = {k: v for k, v in facts.values.items() if k != victim}
    degraded = ResolvedFacts(values=values, missing={**facts.missing, victim: "dropped"})
    outcome = evaluate(INTENTS[action], policy, degraded, evaluated_at=NOW).outcome
    assert outcome is DecisionOutcome.DENY


@settings(max_examples=300, deadline=None)
@given(scenario(), st.sampled_from(list(DecisionOutcome)))
def test_adding_a_rule_never_loosens_the_decision(
    case: tuple[PolicySet, ActionName, ResolvedFacts], extra_outcome: DecisionOutcome
) -> None:
    policy, action, facts = case
    before = evaluate(INTENTS[action], policy, facts, evaluated_at=NOW).outcome
    then: dict[str, Any] = {"decision": extra_outcome.value}
    if extra_outcome is not DecisionOutcome.ALLOW:
        then["reason"] = "NO_APPLICABLE_RULE"
    extra = Rule.model_validate(
        {"id": "EXTRA_RULE", "description": "added", "applies_to": [action.value], "then": then}
    )
    stricter = policy.model_copy(update={"rules": [*policy.rules, extra]})
    after = evaluate(INTENTS[action], stricter, facts, evaluated_at=NOW).outcome
    assert OUTCOME_PRECEDENCE[after] >= OUTCOME_PRECEDENCE[before]
    assert OUTCOME_PRECEDENCE[after] >= OUTCOME_PRECEDENCE[extra_outcome]


@settings(max_examples=200, deadline=None)
@given(scenario())
def test_snapshot_only_contains_required_facts(
    case: tuple[PolicySet, ActionName, ResolvedFacts],
) -> None:
    policy, action, facts = case
    decision = evaluate(INTENTS[action], policy, facts, evaluated_at=NOW)
    read = {k for k in decision.facts_snapshot if not k.startswith("_")}
    assert read <= required_facts(policy, INTENTS[action])


def test_policy_without_rules_for_action_denies() -> None:
    only_escalation = V1.model_copy(
        update={"rules": [r for r in V1.rules if r.id == "ESCALATION_ALLOWED"]}
    )
    decision = evaluate(
        refund(), only_escalation, ResolvedFacts(values={}, missing={}), evaluated_at=NOW
    )
    assert decision.outcome is DecisionOutcome.DENY
    assert decision.rule_results[0].rule_id == "NO_APPLICABLE_RULE"
