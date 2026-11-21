"""Deterministic policy evaluation.

`evaluate()` is pure: same intent + policy + facts + time => same Decision. It performs no
I/O; facts are resolved beforehand by `psa.policy.facts.resolve_facts`. `decide()` is the
thin convenience wrapper that resolves facts and then evaluates.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime

from psa.clock import Clock
from psa.domain import (
    ActionIntent,
    Decision,
    DecisionOutcome,
    ReasonCode,
    RuleResult,
    strictest,
)
from psa.policy.facts import FactContext, FactSource, FactValue, ResolvedFacts, SessionContext
from psa.policy.facts import resolve_facts as _resolve_facts
from psa.policy.schema import (
    PLACEHOLDER,
    AllOf,
    AnyOf,
    Condition,
    NotOf,
    Op,
    Outcome,
    PolicySet,
    Predicate,
    Rule,
)

NO_APPLICABLE_RULE_ID = "NO_APPLICABLE_RULE"


class _MissingFactError(Exception):
    def __init__(self, fact: str) -> None:
        super().__init__(fact)
        self.fact = fact


@dataclass
class _Reader:
    """Tracks exactly which facts a decision read, for the audit snapshot."""

    facts: ResolvedFacts
    read: dict[str, FactValue] = field(default_factory=dict[str, FactValue])
    missing_read: dict[str, str] = field(default_factory=dict[str, str])

    def get(self, name: str) -> FactValue:
        if name in self.facts.values:
            value = self.facts.values[name]
            self.read[name] = value
            return value
        self.missing_read[name] = self.facts.missing.get(name, "not resolved")
        raise _MissingFactError(name)

    def has(self, name: str) -> bool:
        present = name in self.facts.values
        if present:
            self.read[name] = self.facts.values[name]
        else:
            self.missing_read[name] = self.facts.missing.get(name, "not resolved")
        return present


def _compare(op: Op, left: FactValue, right: object) -> bool:
    match op:
        case Op.EQ:
            return left == right and type(left) is type(right)
        case Op.NE:
            return not (left == right and type(left) is type(right))
        case Op.IN:
            return isinstance(right, list) and left in right
        case Op.NOT_IN:
            return isinstance(right, list) and left not in right
        case Op.LT | Op.LTE | Op.GT | Op.GTE:
            if not isinstance(left, int) or not isinstance(right, int):
                raise TypeError(f"op {op} requires integers, got {left!r} and {right!r}")
            if isinstance(left, bool) or isinstance(right, bool):
                raise TypeError(f"op {op} requires integers, not booleans")
            if op is Op.LT:
                return left < right
            if op is Op.LTE:
                return left <= right
            if op is Op.GT:
                return left > right
            return left >= right
        case Op.EXISTS:  # pragma: no cover - handled before _compare
            raise AssertionError("exists is evaluated without a value")


def _eval_predicate(pred: Predicate, reader: _Reader) -> bool:
    if pred.op is Op.EXISTS:
        return reader.has(pred.fact) is pred.value
    left = reader.get(pred.fact)
    right: object = reader.get(pred.value_from) if pred.value_from is not None else pred.value
    return _compare(pred.op, left, right)


def _eval(cond: Condition, reader: _Reader) -> bool:
    if isinstance(cond, Predicate):
        return _eval_predicate(cond, reader)
    if isinstance(cond, AllOf):
        return all(_eval(child, reader) for child in cond.all)
    if isinstance(cond, AnyOf):
        return any(_eval(child, reader) for child in cond.any)
    if isinstance(cond, NotOf):  # pyright: ignore[reportUnnecessaryIsInstance]
        return not _eval(cond.not_, reader)
    raise TypeError(f"unknown condition node {cond!r}")  # pragma: no cover


def render_message(template: str, values: Mapping[str, FactValue]) -> str:
    """Substitute {fact.name} placeholders. No attribute access or format specs."""

    def _sub(match: re.Match[str]) -> str:
        value = values.get(match.group(1))
        return "unknown" if value is None else str(value)

    return PLACEHOLDER.sub(_sub, template)


def _result(rule: Rule, outcome: Outcome, reader: _Reader) -> RuleResult:
    if outcome.message is not None:
        message = render_message(outcome.message, reader.facts.values)
    elif outcome.decision is DecisionOutcome.ALLOW:
        message = f"Passed: {rule.description}"
    else:
        message = rule.description
    return RuleResult(
        rule_id=rule.id,
        outcome=outcome.decision,
        reason_code=outcome.reason,
        message=message,
    )


def _missing_result(rule: Rule, fact: str) -> RuleResult:
    return RuleResult(
        rule_id=rule.id,
        outcome=DecisionOutcome.DENY,
        reason_code=ReasonCode.MISSING_FACT,
        message=f"Required information is unavailable ({fact}), so this can't be completed.",
    )


def _evaluate_rule(rule: Rule, reader: _Reader) -> RuleResult | None:
    """Return the rule's result, or None if its `only_if` guard excludes it."""
    try:
        if rule.only_if is not None and not _eval(rule.only_if, reader):
            return None
        passed = True if rule.when is None else _eval(rule.when, reader)
    except _MissingFactError as missing:
        return _missing_result(rule, missing.fact)
    except TypeError:
        # A fact had an unexpected type. The loader prevents this for valid policies;
        # if it happens anyway, fail closed rather than crash or allow.
        return _missing_result(rule, "fact with unexpected type")
    return _result(rule, rule.then if passed else rule.else_, reader)


def evaluate(
    intent: ActionIntent,
    policy: PolicySet,
    facts: ResolvedFacts,
    *,
    evaluated_at: datetime,
) -> Decision:
    """Evaluate every applicable rule and combine with strictest-wins precedence.

    Fails closed: an action with no applicable rule, or any rule needing a missing fact,
    yields DENY.
    """
    reader = _Reader(facts)
    results: list[RuleResult] = []
    for rule in policy.rules_for(intent.action):
        result = _evaluate_rule(rule, reader)
        if result is not None:
            results.append(result)

    if not results:
        results.append(
            RuleResult(
                rule_id=NO_APPLICABLE_RULE_ID,
                outcome=DecisionOutcome.DENY,
                reason_code=ReasonCode.NO_APPLICABLE_RULE,
                message="This request isn't covered by policy, so it can't be completed.",
            )
        )

    snapshot: dict[str, object] = dict(sorted(reader.read.items()))
    if reader.missing_read:
        snapshot["_missing"] = dict(sorted(reader.missing_read.items()))

    return Decision(
        intent_id=intent.intent_id,
        outcome=strictest([r.outcome for r in results]),
        rule_results=tuple(results),
        policy_set=policy.policy_set,
        policy_version=policy.version,
        evaluated_at=evaluated_at,
        facts_snapshot=snapshot,
    )


def _condition_facts(cond: Condition) -> Iterator[str]:
    if isinstance(cond, Predicate):
        yield cond.fact
        if cond.value_from is not None:
            yield cond.value_from
    elif isinstance(cond, AllOf):
        for child in cond.all:
            yield from _condition_facts(child)
    elif isinstance(cond, AnyOf):
        for child in cond.any:
            yield from _condition_facts(child)
    else:
        yield from _condition_facts(cond.not_)


def rule_facts(rule: Rule) -> set[str]:
    """Every fact a rule may read, including message placeholders."""
    names: set[str] = set()
    if rule.when is not None:
        names |= set(_condition_facts(rule.when))
    if rule.only_if is not None:
        names |= set(_condition_facts(rule.only_if))
    for outcome in (rule.then, rule.else_):
        if outcome.message:
            names |= set(PLACEHOLDER.findall(outcome.message))
    return names


def required_facts(policy: PolicySet, intent: ActionIntent) -> set[str]:
    names: set[str] = set()
    for rule in policy.rules_for(intent.action):
        names |= rule_facts(rule)
    return names


def decide(
    intent: ActionIntent,
    policy: PolicySet,
    *,
    session: SessionContext,
    source: FactSource,
    clock: Clock,
) -> Decision:
    """Resolve the facts this intent needs from the system of record, then evaluate."""
    ctx = FactContext(intent=intent, session=session, source=source, clock=clock)
    facts = _resolve_facts(required_facts(policy, intent), ctx)
    return evaluate(intent, policy, facts, evaluated_at=ctx.now)
