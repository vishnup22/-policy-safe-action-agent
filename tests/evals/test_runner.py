"""Runner integration and independent judge checks using the frozen reference fakes."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from evals.metrics import metrics, pass_hat_k, percentile
from evals.runner.core import Budget, run_suite, run_trial
from evals.runner.judge import compare, judge_events
from evals.schema import Assertion, Scenario
from evals.validate import materialize_world
from sqlalchemy.orm import Session, sessionmaker
from tests.api.fakes import PersistedFake
from tests.runtime.test_ports import FakeRuntime, ScriptedSimulator

from psa.clock import Clock
from psa.domain import (
    ActionIntent,
    EvalRunReport,
    Event,
    EventType,
    OrderStatus,
    SystemUnderTest,
)
from psa.policy import PolicyRegistry
from psa.runtime.ports import RuntimeConfig, TurnResult
from psa.store import EventLog, database_url
from psa.store.models import OrderRow

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = PolicyRegistry.from_dir(ROOT / "policies")


def scenario(name: str = "refund-in-window") -> Scenario:
    path = next((ROOT / "evals/scenarios").rglob(name + ".yaml"))
    return Scenario.model_validate(yaml.safe_load(path.read_text()))


def event_trace(s: Scenario, amount: int = 10000, *, twice: bool = False) -> list[Event]:
    args = s.expected.executed_actions[0].model_copy(update={"amount_cents": amount})
    intent = ActionIntent(
        intent_id="int_script0001",
        conversation_id="conv_script",
        customer_id=s.session.customer_id,
        args=args,
        justification="Test",
        proposed_at=s.world.now,
        idempotency_key="idem-script-0001",
    )
    events = [
        Event(
            event_id="evt_script0000",
            conversation_id="conv_script",
            seq=0,
            type=EventType.ACTION_PROPOSED,
            at=s.world.now,
            payload={"intent": intent.model_dump(mode="json")},
        )
    ]
    for index in range(1, 3 if twice else 2):
        events.append(
            Event(
                event_id=f"evt_script{index:04d}",
                conversation_id="conv_script",
                seq=index,
                type=EventType.ACTION_EXECUTED,
                at=s.world.now,
                policy_version=s.policy.version,
                payload={
                    "intent_id": intent.intent_id,
                    "idempotency_key": intent.idempotency_key,
                    "result": {},
                },
            )
        )
    return events


def test_independent_authorization_and_duplicate_effects() -> None:
    s = scenario()
    world = materialize_world(s)
    okay = judge_events(s, world, event_trace(s), REGISTRY)
    assert not okay.errors
    duplicate = judge_events(s, world, event_trace(s, twice=True), REGISTRY)
    assert duplicate.duplicates == 1
    assert len(duplicate.unauthorized) == 1
    # No POLICY_DECISION event exists: the independent engine must still reject overspend.
    excess = judge_events(s, world, event_trace(s, 10001), REGISTRY)
    assert excess.unauthorized
    denied = scenario("refund-one-cent-over-remaining")
    forbidden = judge_events(denied, materialize_world(denied), event_trace(s, 5001), REGISTRY)
    assert any("forbidden action" in e for e in forbidden.errors)


def test_judge_uses_execution_time_and_authoritative_version() -> None:
    s = scenario("refund-day-thirty")
    events = event_trace(s)
    events[-1] = events[-1].model_copy(update={"at": s.world.now + timedelta(days=1)})
    assert judge_events(s, materialize_world(s), events, REGISTRY).unauthorized
    events = event_trace(s)
    judged = judge_events(s, materialize_world(s), events, REGISTRY, version_at={1: "2026.11.21-2"})
    assert judged.unauthorized
    assert any("active policy" in error for error in judged.errors)


@pytest.mark.parametrize(
    ("op", "actual", "value", "expected"),
    [
        ("eq", 1, 1, True),
        ("ne", 1, 2, True),
        ("lt", 1, 2, True),
        ("lte", 2, 2, True),
        ("gt", 2, 1, True),
        ("gte", 2, 2, True),
        ("in", "a", ["a"], True),
        ("not_in", "b", ["a"], True),
        ("exists", None, False, True),
        ("eq", 1, 2, False),
        ("exists", 0, True, True),
    ],
)
def test_assertion_operators(op: str, actual: object, value: object, expected: bool) -> None:
    assertion = Assertion.model_validate(
        {
            "entity": "order",
            "id": "ord_900001",
            "field": "amount_paid_cents",
            "op": op,
            "value": value,
        }
    )
    assert compare(actual, assertion) == expected


def test_pass_k_hand_calculation() -> None:
    values = [[True, True, True, False], [True, True, False, False]]
    assert pass_hat_k(values, 1) == pytest.approx(0.625)
    assert pass_hat_k(values, 2) == pytest.approx((3 / 6 + 1 / 6) / 2)
    assert pass_hat_k(values, 3) == pytest.approx(0.125)
    assert pass_hat_k(values, 4) == 0
    with pytest.raises(ValueError):
        pass_hat_k(values, 5)
    assert percentile([10, 20, 30], 0.5) == 20
    assert percentile([10, 20, 30], 0.95) == 29


@pytest.mark.db
def test_reference_fake_and_scripted_simulator(sessions: sessionmaker[Session]) -> None:
    calls = []

    def factory(
        config: RuntimeConfig, *, sessions: sessionmaker[Session], clock: Clock
    ) -> FakeRuntime:
        calls.append(config)
        return FakeRuntime(config)

    s = scenario("refund-timeout-retry")
    record = run_trial(
        s,
        SystemUnderTest.GUARDED,
        0,
        runtime_factory=factory,
        simulator=ScriptedSimulator(["second message"]),
        sessions=sessions,
        registry=REGISTRY,
        budget=Budget(1),
    )
    assert record.result.turns == 2
    assert not record.result.success  # An echo must never masquerade as a successful refund.
    assert calls[0].faults[0].mode.value == "timeout"


class RefundRuntime(PersistedFake):
    def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
        s = scenario()
        trace = event_trace(s)
        intent = ActionIntent.model_validate(trace[0].payload["intent"]).model_copy(
            update={"conversation_id": conversation_id}
        )
        with self.sessions.begin() as db:
            log = EventLog(db)
            events = [
                log.append(
                    conversation_id,
                    EventType.ACTION_PROPOSED,
                    at=self.clock.now(),
                    payload={"intent": intent.model_dump(mode="json")},
                )
            ]
            row = db.get(OrderRow, "ord_900001")
            assert row is not None
            row.amount_refunded_cents += 10000
            row.status = OrderStatus.REFUNDED
            events.append(
                log.append(
                    conversation_id,
                    EventType.ACTION_EXECUTED,
                    at=self.clock.now(),
                    policy_version=self.config.policy_version,
                    payload={
                        "intent_id": intent.intent_id,
                        "idempotency_key": intent.idempotency_key,
                        "result": {},
                    },
                )
            )
            events.append(
                log.append(
                    conversation_id,
                    EventType.MODEL_CALL,
                    at=self.clock.now(),
                    payload={
                        "model": "scripted",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "latency_ms": 20,
                        "cost_usd": 0.25,
                    },
                )
            )
        return TurnResult(
            conversation_id=conversation_id, reply_text="Refunded", events=tuple(events)
        )


@pytest.mark.db
def test_effects_final_state_budget_and_metrics(sessions: sessionmaker[Session]) -> None:
    budget = Budget(0.1)
    record = run_trial(
        scenario(),
        SystemUnderTest.GUARDED,
        0,
        runtime_factory=RefundRuntime,
        simulator=ScriptedSimulator(["must never execute"]),
        sessions=sessions,
        registry=REGISTRY,
        budget=budget,
    )
    assert record.result.turns == 1
    assert budget.spent == 0.25
    assert record.result.failure_reason == "budget exhausted"
    assert not record.result.unauthorized_actions
    summary = metrics(SystemUnderTest.GUARDED, [record])
    assert summary.unauthorized_action_rate == 0
    assert summary.latency_ms_p95 == 20


@pytest.mark.db
def test_policy_change_and_clock_events(sessions: sessionmaker[Session]) -> None:
    seen = []

    class Observer(PersistedFake):
        def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
            seen.append((self.config.policy_version, self.clock.now()))
            return super().handle_user_message(conversation_id, text)

    s = scenario("policy-switch-day-20")
    run_trial(
        s,
        SystemUnderTest.GUARDED,
        0,
        runtime_factory=Observer,
        simulator=ScriptedSimulator(["refund now"]),
        sessions=sessions,
        registry=REGISTRY,
        budget=Budget(1),
    )
    assert [version for version, _ in seen] == ["2026.11.21-1", "2026.11.21-2"]


@pytest.mark.db
def test_parallel_isolation_resume_and_report(tmp_path: Path) -> None:
    from tests.store.conftest import _reachable

    from psa.store import database_url

    if not _reachable(database_url()):
        pytest.skip("Postgres unavailable")
    kwargs: dict[str, Any] = dict(
        systems=[SystemUnderTest.BASELINE, SystemUnderTest.GUARDED],
        trials=1,
        runtime_factory=PersistedFake,
        simulator_factory=lambda: ScriptedSimulator([]),
        url=database_url(),
        policies_dir=ROOT / "policies",
        reports_dir=tmp_path,
        suite="test",
        run_id="run_test",
        workers=2,
    )
    report = run_suite([scenario()], **kwargs)
    parsed = EvalRunReport.model_validate_json((tmp_path / "run_test.json").read_text())
    assert parsed == report
    assert len(report.scenarios) == 2
    assert all(len(row.trials) == 1 for row in report.scenarios)
    resumed = run_suite([scenario()], resume=True, **kwargs)
    assert resumed.scenarios == report.scenarios
    assert "| baseline |" in (tmp_path / "run_test.md").read_text()
    with pytest.raises(ValueError, match="inputs differ"):
        run_suite([scenario("refund-day-thirty")], resume=True, **kwargs)

    kwargs.update(
        systems=[SystemUnderTest.GUARDED],
        runtime_factory=RefundRuntime,
        run_id="run_budget_resume",
    )
    interrupted = run_suite([scenario()], max_cost_usd=0.1, **kwargs)
    first_attempt = interrupted.scenarios[0].trials[0]
    assert first_attempt.failure_reason == "budget exhausted"

    still_stopped = run_suite([scenario()], resume=True, max_cost_usd=0.25, **kwargs)
    assert still_stopped.scenarios == interrupted.scenarios

    retried = run_suite([scenario()], resume=True, max_cost_usd=1, **kwargs)
    assert len(retried.scenarios[0].trials) == 1
    attempt = retried.scenarios[0].trials[0]
    assert attempt.success


@pytest.mark.db
def test_audit_uses_store_facts_not_runtime_claims(sessions: sessionmaker[Session]) -> None:
    record = run_trial(
        scenario("refund-day-thirty-one"),
        SystemUnderTest.BASELINE,
        0,
        runtime_factory=RefundRuntime,
        simulator=ScriptedSimulator([]),
        sessions=sessions,
        registry=REGISTRY,
        budget=Budget(1),
    )
    assert record.result.unauthorized_actions
    assert "independent policy" in (record.result.failure_reason or "")


@pytest.mark.db
def test_infrastructure_errors_are_excluded_and_retried(
    sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    attempts = 0

    class UnreliableRuntime(RefundRuntime):
        def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return TurnResult(
                    conversation_id=conversation_id,
                    reply_text="Unavailable",
                    infrastructure_error="model unavailable",
                )
            if attempts == 2:
                raise TimeoutError("runtime unavailable")
            return super().handle_user_message(conversation_id, text)

    kwargs: dict[str, Any] = dict(
        systems=[SystemUnderTest.GUARDED],
        trials=3,
        runtime_factory=UnreliableRuntime,
        simulator_factory=lambda: ScriptedSimulator([]),
        url=database_url(),
        policies_dir=ROOT / "policies",
        reports_dir=tmp_path,
        suite="test",
        run_id="outage",
    )
    partial = run_suite([scenario()], **kwargs)
    assert partial.systems[0].task_success_rate == 1
    assert partial.systems[0].pass_hat_k == {1: 1}
    assert len(partial.scenarios[0].trials) == 1
    assert "| guarded | 1 | 2 |" in (tmp_path / "outage.md").read_text(encoding="utf-8")
    resumed = run_suite([scenario()], resume=True, **kwargs)
    assert attempts == 5
    assert resumed.systems[0].pass_hat_k == {1: 1, 2: 1, 3: 1}


@pytest.mark.db
def test_budget_zero_never_calls_runtime(sessions: sessionmaker[Session]) -> None:
    class NeverCall(PersistedFake):
        def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
            pytest.fail("budget should stop the first billable call")

    record = run_trial(
        scenario(),
        SystemUnderTest.GUARDED,
        0,
        runtime_factory=NeverCall,
        simulator=ScriptedSimulator([]),
        sessions=sessions,
        registry=REGISTRY,
        budget=Budget(0),
    )
    assert record.result.turns == 0
    assert "budget exhausted" in (record.result.failure_reason or "")
