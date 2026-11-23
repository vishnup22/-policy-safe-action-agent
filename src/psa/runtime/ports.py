"""Ports between lanes. Frozen for Days 2-4; change only via a coordinated PR.

Implemented by the agent lane (Claude Code):  AgentRuntime, RuntimeFactory, UserSimulator
Consumed by the API + eval lane (Codex):       psa.api (HTTP) and evals.runner (scenarios)

The API and the eval runner must depend ONLY on these protocols, never on concrete agent
classes, so both lanes can build and test in parallel (Codex uses fakes until the real
runtime merges; final wiring happens in T4.5).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from psa.clock import Clock
from psa.domain import Event, SystemUnderTest

if TYPE_CHECKING:
    from evals.schema import Scenario


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FaultMode(StrEnum):
    TIMEOUT = "timeout"
    ERROR_5XX = "error_5xx"
    CARD_DECLINED = "card_declined"
    RATE_LIMITED = "rate_limited"


class ToolFault(_Frozen):
    """Make the Nth call (1-based) of `tool` fail in the given way. Mirrors evals.schema.Fault."""

    tool: str = Field(min_length=1)
    mode: FaultMode
    on_call: int = Field(ge=1)


class RuntimeConfig(_Frozen):
    system: SystemUnderTest
    policy_set: str = "larkspur-returns"
    policy_version: str
    faults: tuple[ToolFault, ...] = ()
    max_agent_steps: int = Field(default=12, ge=1, description="Tool/model steps per user turn")


class SessionStart(_Frozen):
    """Server-side session state at conversation start (verification flow lands Day 6)."""

    customer_id: str | None
    identity_verified: bool = False


class TurnResult(_Frozen):
    conversation_id: str
    reply_text: str
    events: tuple[Event, ...] = Field(
        default=(), description="Every event appended during this turn, in order"
    )
    pending_approval_id: str | None = None
    ended: bool = False


class ApprovalResolution(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


@runtime_checkable
class AgentRuntime(Protocol):
    """One configured agent (baseline or guarded) operating on one database.

    All methods are synchronous and transactional: every event of a call is committed to the
    event log before the call returns.
    """

    @property
    def config(self) -> RuntimeConfig: ...

    def start_conversation(self, session: SessionStart) -> str:
        """Create a conversation and return its id. Appends CONVERSATION_STARTED."""
        ...

    def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
        """Run one user turn to completion (tool calls, proposals, decisions, executions)."""
        ...

    def resolve_approval(
        self,
        approval_id: str,
        resolution: ApprovalResolution,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> TurnResult:
        """Resolve a REQUIRE_APPROVAL intent; on approval the executor runs it."""
        ...

    def set_policy_version(self, version: str) -> None:
        """Switch policy version mid-conversation (stale-policy scenarios)."""
        ...


class RuntimeFactory(Protocol):
    def __call__(
        self, config: RuntimeConfig, *, sessions: sessionmaker[Session], clock: Clock
    ) -> AgentRuntime: ...


class SimulatorTurn(_Frozen):
    role: Literal["user", "agent"]
    text: str


@runtime_checkable
class UserSimulator(Protocol):
    """LLM-driven simulated customer. The runner sends `scenario.opening_message` itself."""

    def next_message(self, scenario: Scenario, transcript: Sequence[SimulatorTurn]) -> str | None:
        """Return the customer's next message, or None when the customer is done."""
        ...
