"""Human-in-the-loop approvals for REQUIRE_APPROVAL decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from psa.clock import Clock
from psa.domain import ActionIntent, Decision, EventType
from psa.runtime.ports import ApprovalResolution
from psa.store import EventLog, new_id
from psa.store.models import ApprovalRow, ApprovalStatus, ConversationRow, ConversationStatus


class ApprovalError(LookupError):
    pass


class ApprovalAlreadyResolvedError(ApprovalError):
    pass


@dataclass(frozen=True)
class ResolvedApproval:
    approval_id: str
    conversation_id: str
    intent: ActionIntent
    decision: Decision
    resolution: ApprovalResolution


def request_approval(
    db: Session, log: EventLog, clock: Clock, intent: ActionIntent, decision: Decision
) -> str:
    approval_id = new_id("apr")
    now = clock.now()
    db.add(
        ApprovalRow(
            approval_id=approval_id,
            conversation_id=intent.conversation_id,
            intent_id=intent.intent_id,
            intent=intent.model_dump(mode="json"),
            decision=decision.model_dump(mode="json"),
            status=ApprovalStatus.PENDING,
            requested_at=now,
        )
    )
    conversation = db.get(ConversationRow, intent.conversation_id)
    if conversation is not None:
        conversation.status = ConversationStatus.AWAITING_APPROVAL
    db.flush()
    log.append(
        intent.conversation_id,
        EventType.APPROVAL_REQUESTED,
        at=now,
        payload={"approval_id": approval_id, "intent_id": intent.intent_id},
    )
    return approval_id


def resolve_approval(
    db: Session,
    log: EventLog,
    clock: Clock,
    approval_id: str,
    resolution: ApprovalResolution,
    *,
    reviewer: str,
    note: str | None,
) -> ResolvedApproval:
    row = db.get(ApprovalRow, approval_id, with_for_update=True)
    if row is None:
        raise ApprovalError(f"approval {approval_id} not found")
    if row.status is not ApprovalStatus.PENDING:
        raise ApprovalAlreadyResolvedError(f"approval {approval_id} is already {row.status}")
    now = clock.now()
    row.status = (
        ApprovalStatus.APPROVED
        if resolution is ApprovalResolution.APPROVED
        else ApprovalStatus.REJECTED
    )
    row.resolved_at = now
    row.reviewer = reviewer
    row.note = note
    conversation = db.get(ConversationRow, row.conversation_id)
    if conversation is not None:
        conversation.status = ConversationStatus.ACTIVE
    db.flush()
    payload: dict[str, Any] = {
        "approval_id": approval_id,
        "resolution": resolution.value,
        "reviewer": reviewer,
        "note": note,
    }
    log.append(row.conversation_id, EventType.APPROVAL_RESOLVED, at=now, payload=payload)
    return ResolvedApproval(
        approval_id=approval_id,
        conversation_id=row.conversation_id,
        intent=ActionIntent.model_validate(row.intent),
        decision=Decision.model_validate(row.decision),
        resolution=resolution,
    )
