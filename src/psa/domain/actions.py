"""Action intents: the ONLY way the agent can request a side effect.

The LLM emits an ActionIntent via `propose_action`; the policy engine evaluates it;
the executor runs it only if the decision is ALLOW (or an approval resolves it).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from psa.domain.commerce import Address


class ActionName(StrEnum):
    ISSUE_REFUND = "issue_refund"
    ISSUE_STORE_CREDIT = "issue_store_credit"
    CANCEL_ORDER = "cancel_order"
    UPDATE_ADDRESS = "update_address"
    CREATE_TICKET = "create_ticket"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    SCHEDULE_FOLLOW_UP = "schedule_follow_up"


SIDE_EFFECTING_ACTIONS: frozenset[ActionName] = frozenset(ActionName)
"""Every action is side-effecting; read tools are not actions."""

MONEY_ACTIONS: frozenset[ActionName] = frozenset(
    {ActionName.ISSUE_REFUND, ActionName.ISSUE_STORE_CREDIT}
)


class _Args(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IssueRefundArgs(_Args):
    action: Literal[ActionName.ISSUE_REFUND] = ActionName.ISSUE_REFUND
    order_id: str
    amount_cents: int = Field(gt=0)
    item_skus: tuple[str, ...] = Field(
        default=(), description="Items being refunded; empty means order-level refund"
    )
    reason: str = Field(min_length=1, max_length=500)


class IssueStoreCreditArgs(_Args):
    action: Literal[ActionName.ISSUE_STORE_CREDIT] = ActionName.ISSUE_STORE_CREDIT
    customer_id: str
    order_id: str | None = None
    amount_cents: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class CancelOrderArgs(_Args):
    action: Literal[ActionName.CANCEL_ORDER] = ActionName.CANCEL_ORDER
    order_id: str
    reason: str = Field(min_length=1, max_length=500)


class UpdateAddressArgs(_Args):
    action: Literal[ActionName.UPDATE_ADDRESS] = ActionName.UPDATE_ADDRESS
    order_id: str
    new_address: Address


class CreateTicketArgs(_Args):
    action: Literal[ActionName.CREATE_TICKET] = ActionName.CREATE_TICKET
    order_id: str | None = None
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=4000)


class EscalationPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class EscalateToHumanArgs(_Args):
    action: Literal[ActionName.ESCALATE_TO_HUMAN] = ActionName.ESCALATE_TO_HUMAN
    reason: str = Field(min_length=1, max_length=500)
    priority: EscalationPriority = EscalationPriority.NORMAL


class ScheduleFollowUpArgs(_Args):
    action: Literal[ActionName.SCHEDULE_FOLLOW_UP] = ActionName.SCHEDULE_FOLLOW_UP
    due_at: datetime
    order_id: str | None = None
    note: str = Field(min_length=1, max_length=1000)


ActionArgs = Annotated[
    IssueRefundArgs
    | IssueStoreCreditArgs
    | CancelOrderArgs
    | UpdateAddressArgs
    | CreateTicketArgs
    | EscalateToHumanArgs
    | ScheduleFollowUpArgs,
    Field(discriminator="action"),
]


class ActionIntent(BaseModel):
    """A proposed side effect. Immutable once created; identified by intent_id."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    intent_id: str = Field(pattern=r"^int_[A-Za-z0-9]{8,}$")
    conversation_id: str
    customer_id: str | None = Field(
        default=None, description="Authenticated/verified customer for this session, if any"
    )
    args: ActionArgs
    justification: str = Field(
        min_length=1, max_length=1000, description="Agent's stated reason; never used as a fact"
    )
    proposed_at: datetime
    idempotency_key: str = Field(
        min_length=8, description="Stable across retries of the same intent"
    )

    @property
    def action(self) -> ActionName:
        return self.args.action
