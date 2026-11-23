from functools import partial

import pytest
from evals.runner.core import Budget, run_trial
from sqlalchemy.orm import Session, sessionmaker
from tests.agent.conftest import propose
from tests.evals.test_runner import REGISTRY, scenario
from tests.runtime.test_ports import ScriptedSimulator

from psa.domain import SystemUnderTest
from psa.llm.scripted import ScriptedLLM, Step
from psa.runtime.factory import build_runtime
from psa.tools import SimulatedStripe

pytestmark = pytest.mark.db


@pytest.mark.parametrize("mode", ["approve", "reject", "resolve-twice"])
def test_scenario_operator_drives_approval_workflow(
    sessions: sessionmaker[Session], mode: str
) -> None:
    s = scenario(f"high-value-{mode}-22000")
    scripted = ScriptedLLM.from_steps(
        [
            propose("issue_refund", order_id="ord_900001", amount_cents=22000, reason="Return"),
            Step(text="Waiting for a review."),
        ]
    )
    gateway = SimulatedStripe()
    record = run_trial(
        s,
        SystemUnderTest.GUARDED,
        0,
        runtime_factory=partial(build_runtime, llm=scripted, payments=gateway, registry=REGISTRY),
        simulator=ScriptedSimulator([]),
        sessions=sessions,
        registry=REGISTRY,
        budget=Budget(1),
    )
    assert record.result.success, record.result.failure_reason
    assert not record.result.unauthorized_actions
    assert gateway.calls == (0 if mode == "reject" else 1)


def test_follow_up_fires_after_scenario_clock_advances(sessions: sessionmaker[Session]) -> None:
    s = scenario("follow-up-fires-one-hour")
    action = s.expected.executed_actions[0].model_dump(mode="json", exclude={"action"})
    scripted = ScriptedLLM.from_steps(
        [
            propose("schedule_follow_up", **action),
            Step(text="Reminder scheduled."),
        ]
    )
    record = run_trial(
        s,
        SystemUnderTest.GUARDED,
        0,
        runtime_factory=partial(
            build_runtime, llm=scripted, payments=SimulatedStripe(), registry=REGISTRY
        ),
        simulator=ScriptedSimulator([]),
        sessions=sessions,
        registry=REGISTRY,
        budget=Budget(1),
    )
    assert record.result.success, record.result.failure_reason
