"""Eval report contract shared by the eval runner (producer) and the web UI (consumer)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from psa.domain.actions import ActionName


class SystemUnderTest(StrEnum):
    BASELINE = "baseline"
    GUARDED = "guarded"


class ScenarioCategory(StrEnum):
    HAPPY_PATH = "happy_path"
    POLICY_BOUNDARY = "policy_boundary"
    POLICY_BAIT = "policy_bait"
    PROMPT_INJECTION = "prompt_injection"
    IDENTITY = "identity"
    STALE_POLICY = "stale_policy"
    TOOL_FAILURE = "tool_failure"
    IDEMPOTENCY = "idempotency"
    MULTI_INTENT = "multi_intent"
    ESCALATION = "escalation"
    FOLLOW_UP = "follow_up"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TrialResult(_Frozen):
    trial: int = Field(ge=0)
    success: bool
    unauthorized_actions: tuple[ActionName, ...] = ()
    false_refusal: bool = False
    escalated: bool = False
    turns: int = Field(ge=0)
    latency_ms_p50: float = Field(ge=0)
    latency_ms_p95: float = Field(ge=0)
    cost_usd: float = Field(ge=0)
    conversation_id: str
    failure_reason: str | None = None


class ScenarioResult(_Frozen):
    scenario_id: str
    category: ScenarioCategory
    system: SystemUnderTest
    trials: tuple[TrialResult, ...]


class SystemMetrics(_Frozen):
    system: SystemUnderTest
    scenarios: int
    trials_per_scenario: int
    task_success_rate: float = Field(ge=0, le=1)
    unauthorized_action_rate: float = Field(ge=0, le=1)
    false_refusal_rate: float = Field(ge=0, le=1)
    correct_escalation_rate: float = Field(ge=0, le=1)
    injection_resistance_rate: float = Field(ge=0, le=1)
    duplicate_side_effects: int = Field(ge=0)
    pass_hat_k: dict[int, float] = Field(description="k -> pass^k, k = 1..trials_per_scenario")
    latency_ms_p50: float = Field(ge=0)
    latency_ms_p95: float = Field(ge=0)
    cost_usd_per_resolved: float = Field(ge=0)
    by_category: dict[ScenarioCategory, float] = Field(description="category -> success rate")


class EvalRunReport(_Frozen):
    run_id: str
    suite: str = Field(description="e.g. 'regression' or 'full'")
    started_at: datetime
    finished_at: datetime
    git_sha: str
    policy_version: str
    agent_model: str
    simulator_model: str
    systems: tuple[SystemMetrics, ...]
    scenarios: tuple[ScenarioResult, ...]
