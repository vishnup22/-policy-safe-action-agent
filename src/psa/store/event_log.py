"""Append-only event log with gap-free per-conversation sequence numbers.

Sequence allocation increments `conversations.next_seq` with UPDATE ... RETURNING inside
the caller's transaction. The row lock serializes concurrent appenders, and a rolled-back
transaction rolls back the counter too, so sequences never have gaps.
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from psa.domain import Event, EventType
from psa.store.models import ConversationRow, ConversationStatus, EventRow

POLICY_VERSIONED_EVENTS = frozenset({EventType.POLICY_DECISION, EventType.ACTION_EXECUTED})


class UnknownConversationError(LookupError):
    pass


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _to_event(row: EventRow) -> Event:
    return Event(
        event_id=row.event_id,
        conversation_id=row.conversation_id,
        seq=row.seq,
        type=row.type,
        at=row.at,
        policy_version=row.policy_version,
        payload=row.payload,
    )


class EventLog:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start_conversation(
        self,
        *,
        at: datetime,
        customer_id: str | None = None,
        conversation_id: str | None = None,
    ) -> str:
        conversation_id = conversation_id or new_id("conv")
        self._session.add(
            ConversationRow(
                conversation_id=conversation_id,
                customer_id=customer_id,
                identity_verified=False,
                status=ConversationStatus.ACTIVE,
                started_at=at,
                next_seq=0,
            )
        )
        self._session.flush()
        self.append(
            conversation_id,
            EventType.CONVERSATION_STARTED,
            at=at,
            payload={"customer_id": customer_id},
        )
        return conversation_id

    def append(
        self,
        conversation_id: str,
        type: EventType,
        *,
        at: datetime,
        payload: dict[str, Any] | None = None,
        policy_version: str | None = None,
    ) -> Event:
        if type in POLICY_VERSIONED_EVENTS and policy_version is None:
            raise ValueError(f"{type} events must record the policy version")
        seq = self._session.execute(
            update(ConversationRow)
            .where(ConversationRow.conversation_id == conversation_id)
            .values(next_seq=ConversationRow.next_seq + 1)
            .returning(ConversationRow.next_seq - 1)
        ).scalar_one_or_none()
        if seq is None:
            raise UnknownConversationError(conversation_id)
        row = EventRow(
            event_id=new_id("evt"),
            conversation_id=conversation_id,
            seq=seq,
            type=type,
            at=at,
            policy_version=policy_version,
            payload=payload or {},
        )
        self._session.add(row)
        self._session.flush()
        return _to_event(row)

    def read(self, conversation_id: str) -> list[Event]:
        rows = self._session.scalars(
            select(EventRow)
            .where(EventRow.conversation_id == conversation_id)
            .order_by(EventRow.seq)
        )
        return [_to_event(row) for row in rows]
