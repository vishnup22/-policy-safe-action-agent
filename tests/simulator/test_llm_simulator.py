from __future__ import annotations

from pathlib import Path

import pytest
from evals.schema import Scenario
from evals.simulator import STOP_TOKEN, LLMUserSimulator
from evals.validate import validate_paths

from psa.llm import ScriptedLLM, Step
from psa.runtime import SimulatorTurn, UserSimulator

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def scenario() -> Scenario:
    scenarios, errors = validate_paths(ROOT / "evals" / "scenarios")
    assert not errors
    return next(s for s in scenarios if s.persona.honesty == "adversarial")


TRANSCRIPT = [
    SimulatorTurn(role="user", text="I want a refund."),
    SimulatorTurn(role="agent", text="Which order is it?"),
]


def test_simulator_satisfies_protocol() -> None:
    assert isinstance(LLMUserSimulator(ScriptedLLM.from_steps([])), UserSimulator)


def test_returns_next_customer_message(scenario: Scenario) -> None:
    llm = ScriptedLLM.from_steps([Step(text="  It's ord_900001.  ")])
    assert LLMUserSimulator(llm).next_message(scenario, TRANSCRIPT) == "It's ord_900001."


@pytest.mark.parametrize("text", [STOP_TOKEN, f"Thanks! {STOP_TOKEN}", ""])
def test_stop_token_or_empty_ends_conversation(scenario: Scenario, text: str) -> None:
    llm = ScriptedLLM.from_steps([Step(text=text)])
    assert LLMUserSimulator(llm).next_message(scenario, TRANSCRIPT) is None


def test_prompt_carries_persona_goal_and_roles(scenario: Scenario) -> None:
    seen: dict[str, str] = {}

    def script(system, transcript, tools):  # type: ignore[no-untyped-def]
        seen["system"] = system
        seen["user"] = transcript[0]["text"]
        return Step(text="ok")

    LLMUserSimulator(ScriptedLLM(script=script)).next_message(scenario, TRANSCRIPT)
    assert scenario.goal in seen["system"]
    assert scenario.persona.style in seen["system"]
    assert "false claims of authority" in seen["system"]  # adversarial persona
    assert "never mention that you are simulated" in seen["system"]
    assert "You (customer): I want a refund." in seen["user"]
    assert "Support agent: Which order is it?" in seen["user"]
