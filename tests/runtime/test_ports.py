"""Contract tests for the runtime ports, plus reference fakes other lanes can copy."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from evals.schema import Fault, Scenario
from pydantic import ValidationError

from psa.domain import SystemUnderTest
from psa.runtime import (
    AgentRuntime,
    ApprovalResolution,
    FaultMode,
    RuntimeConfig,
    SessionStart,
    SimulatorTurn,
    ToolFault,
    TurnResult,
    UserSimulator,
)


class FakeRuntime:
    """Minimal in-memory AgentRuntime: echoes messages, never takes actions."""

    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config
        self._next = 0

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    def start_conversation(self, session: SessionStart) -> str:
        self._next += 1
        return f"conv_fake{self._next:04d}"

    def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
        return TurnResult(conversation_id=conversation_id, reply_text=f"echo: {text}")

    def resolve_approval(
        self,
        approval_id: str,
        resolution: ApprovalResolution,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> TurnResult:
        return TurnResult(conversation_id="conv_fake0001", reply_text=resolution.value)

    def set_policy_version(self, version: str) -> None:
        self._config = self._config.model_copy(update={"policy_version": version})


class ScriptedSimulator:
    """UserSimulator that replays fixed lines, then stops."""

    def __init__(self, lines: Sequence[str]) -> None:
        self._lines = list(lines)

    def next_message(self, scenario: Scenario, transcript: Sequence[SimulatorTurn]) -> str | None:
        user_turns = sum(1 for t in transcript if t.role == "user")
        index = user_turns - 1  # opening message is sent by the runner
        return self._lines[index] if 0 <= index < len(self._lines) else None


CONFIG = RuntimeConfig(system=SystemUnderTest.GUARDED, policy_version="2026.11.21-1")


def test_fake_runtime_satisfies_protocol() -> None:
    runtime = FakeRuntime(CONFIG)
    assert isinstance(runtime, AgentRuntime)
    conv = runtime.start_conversation(SessionStart(customer_id=None))
    assert runtime.handle_user_message(conv, "hi").reply_text == "echo: hi"
    runtime.set_policy_version("2026.11.21-2")
    assert runtime.config.policy_version == "2026.11.21-2"


def test_scripted_simulator_satisfies_protocol() -> None:
    assert isinstance(ScriptedSimulator(["more"]), UserSimulator)


def test_tool_fault_mirrors_scenario_fault_schema() -> None:
    """evals.schema.Fault and ports.ToolFault must stay convertible field-for-field."""
    fault = Fault(tool="issue_refund", mode="card_declined", on_call=1)
    converted = ToolFault.model_validate(fault.model_dump())
    assert converted.mode is FaultMode.CARD_DECLINED
    assert set(ToolFault.model_fields) == set(Fault.model_fields)


def test_config_is_strict() -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate(
            {"system": "guarded", "policy_version": "2026.11.21-1", "temperature": 2}
        )
