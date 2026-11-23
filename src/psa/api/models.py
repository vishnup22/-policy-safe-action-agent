"""HTTP-only schemas; domain objects retain their frozen shared contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from psa.domain import ActionIntent, ActionName, Decision, Event


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class LoginRequest(Model):
    passcode: str


class LoginResponse(Model):
    token: str
    expires_at: datetime


class ConversationRequest(Model):
    customer_email: str | None = None


class ConversationCreated(Model):
    conversation_id: str
    started_at: datetime


class ConversationSummary(ConversationCreated):
    last_event_at: datetime
    customer_id: str | None
    status: Literal["active", "ended", "awaiting_approval"]
    message_count: int
    actions_executed: int
    actions_blocked: int


class Conversations(Model):
    items: list[ConversationSummary]
    next_cursor: str | None = None


class MessageRequest(Model):
    text: str = Field(min_length=1, max_length=20000)


class Reply(Model):
    text: str
    at: datetime


class MessageResponse(Model):
    reply: Reply
    events: tuple[Event, ...]
    pending_approval_id: str | None = None


class EventsResponse(Model):
    conversation_id: str
    events: list[Event]


class Approval(Model):
    approval_id: str
    conversation_id: str
    status: Literal["pending", "approved", "rejected"]
    requested_at: datetime
    intent: ActionIntent
    decision: Decision
    resolved_at: datetime | None
    reviewer: str | None
    note: str | None


class Approvals(Model):
    items: list[Approval]


class ResolveRequest(Model):
    resolution: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=4000)


class PolicySummary(Model):
    policy_set: str
    version: str
    rule_count: int
    updated_at: datetime


class Policies(Model):
    items: list[PolicySummary]


class PolicyRule(Model):
    id: str
    applies_to: tuple[ActionName, ...]
    description: str


class PolicyDetail(Model):
    policy_set: str
    version: str
    yaml: str
    rules: list[PolicyRule]


class Headline(Model):
    task_success_rate: float
    unauthorized_action_rate: float


class RunSummary(Model):
    run_id: str
    suite: str
    started_at: datetime
    finished_at: datetime
    git_sha: str
    policy_version: str
    headline: dict[str, Headline]


class Runs(Model):
    items: list[RunSummary]


class Health(Model):
    status: Literal["ok"] = "ok"
    version: str = "0.1.0"
    policy_version: str


class ErrorDetail(Model):
    code: str
    message: str


class ErrorResponse(Model):
    error: ErrorDetail
