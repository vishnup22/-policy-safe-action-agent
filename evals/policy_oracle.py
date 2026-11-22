"""Complete forbidden patterns into concrete policy probes, independent of chat claims."""

from datetime import timedelta
from typing import Any

from pydantic import TypeAdapter

from evals.runner.facts import WorldFacts
from evals.schema import ForbiddenAction, Scenario
from evals.validate import materialize_world
from psa.clock import SimulatedClock
from psa.domain import ActionArgs, ActionIntent, Decision, DecisionOutcome
from psa.policy import PolicyRegistry, SessionContext, decide


def merge(target: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = target.copy()
    for key, value in patch.items():
        result[key] = merge(result.get(key, {}), value) if isinstance(value, dict) else value
    return result


def probe_args(scenario: Scenario, forbidden: ForbiddenAction) -> ActionArgs:
    world = materialize_world(scenario)
    order_id = str(forbidden.args_match.get("order_id") or scenario.expected.final_state[0].id)
    order = next((o for o in world.orders if o.order_id == order_id), world.orders[-1])
    defaults: dict[str, Any] = {"action": forbidden.action.value}
    action = forbidden.action.value
    if action in {
        "issue_refund",
        "cancel_order",
        "update_address",
        "create_ticket",
        "schedule_follow_up",
    }:
        defaults["order_id"] = order_id
    if action in {"issue_refund", "issue_store_credit", "cancel_order", "escalate_to_human"}:
        defaults["reason"] = "Policy consistency probe"
    if action == "issue_refund":
        defaults["amount_cents"] = max(1, order.amount_refundable_cents)
    if action == "issue_store_credit":
        defaults.update(customer_id=scenario.session.customer_id, amount_cents=5001)
    if action == "update_address":
        defaults["new_address"] = order.shipping_address.model_dump(mode="json")
    if action == "create_ticket":
        defaults.update(subject="Synthetic probe", body="Synthetic support ticket")
    if action == "schedule_follow_up":
        defaults.update(
            due_at=(scenario.world.now + timedelta(days=2)).isoformat(), note="Synthetic check"
        )
    return TypeAdapter(ActionArgs).validate_python(merge(defaults, dict(forbidden.args_match)))


def policy_checks(
    scenario: Scenario, registry: PolicyRegistry
) -> list[tuple[str, Decision, DecisionOutcome]]:
    source = WorldFacts(materialize_world(scenario))
    clock = SimulatedClock(scenario.world.now)
    for advance in scenario.clock_advance:
        if advance.at_turn <= scenario.policy_check_turn:
            clock.advance(advance.by)
    version = scenario.policy.version
    if scenario.policy_change and scenario.policy_change.at_turn <= scenario.policy_check_turn:
        version = scenario.policy_change.to_version
    policy = registry.get(scenario.policy.set, version)
    session = SessionContext(
        "consistency", scenario.session.customer_id, scenario.session.identity_verified
    )
    checks = []
    blocked = {
        "denied": DecisionOutcome.DENY,
        "verification_required": DecisionOutcome.REQUIRE_VERIFICATION,
        "approval_pending": DecisionOutcome.REQUIRE_APPROVAL,
    }.get(scenario.expected.outcome, DecisionOutcome.DENY)
    actions = [("expected", a, DecisionOutcome.ALLOW) for a in scenario.expected.executed_actions]
    actions += [("forbidden", probe_args(scenario, f), blocked) for f in scenario.forbidden_actions]
    for number, (kind, args, expected) in enumerate(actions):
        intent = ActionIntent(
            intent_id=f"int_check{number:08d}",
            conversation_id="consistency",
            customer_id=scenario.session.customer_id,
            args=args,
            justification="Independent policy check",
            proposed_at=clock.now(),
            idempotency_key=f"check-{number:08d}",
        )
        decision = decide(intent, policy, session=session, source=source, clock=clock)
        checks.append((kind, decision, expected))
        # Expected sequential effects alter the available balance for the next expected effect.
        if kind == "expected":
            source.apply(intent, clock.now())
    return checks
