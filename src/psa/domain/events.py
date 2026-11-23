"""Append-only event log contract. Every conversation is a sequence of these."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    CONVERSATION_STARTED = "conversation_started"
    USER_MESSAGE = "user_message"
    AGENT_MESSAGE = "agent_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    MODEL_CALL = "model_call"
    ACTION_PROPOSED = "action_proposed"
    POLICY_DECISION = "policy_decision"
    VERIFICATION_REQUESTED = "verification_requested"
    VERIFICATION_COMPLETED = "verification_completed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    ACTION_EXECUTED = "action_executed"
    ACTION_FAILED = "action_failed"
    FOLLOW_UP_SCHEDULED = "follow_up_scheduled"
    FOLLOW_UP_FIRED = "follow_up_fired"
    CONVERSATION_ENDED = "conversation_ended"


class Event(BaseModel):
    """One immutable log entry. (conversation_id, seq) is unique and gap-free."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(pattern=r"^evt_[A-Za-z0-9]{8,}$")
    conversation_id: str
    seq: int = Field(ge=0)
    type: EventType
    at: datetime
    policy_version: str | None = Field(
        default=None, description="Required on POLICY_DECISION and ACTION_EXECUTED"
    )
    payload: dict[str, Any] = Field(default_factory=dict)
