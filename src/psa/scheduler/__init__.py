"""Durable follow-up scheduler (T6.3).

Follow-ups live in the `follow_ups` table, so they survive process restarts: any
scheduler process started later fires whatever is due at `clock.now()`.

Firing is exactly-once per follow-up even with several workers: rows are claimed with
`SELECT ... FOR UPDATE SKIP LOCKED`, flipped SCHEDULED -> FIRED and the
`follow_up_fired` event is appended in the same transaction. The customer-facing
reminder (an `agent_message`) is deterministic text from the stored note — no model
call — so a replay reproduces it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from psa.clock import Clock
from psa.domain import EventType
from psa.store import EventLog
from psa.store.models import FollowUpRow, FollowUpStatus


@dataclass(frozen=True)
class FiredFollowUp:
    follow_up_id: str
    conversation_id: str
    order_id: str | None
    due_at: datetime
    fired_at: datetime
    note: str


def reminder_text(follow_up: FiredFollowUp) -> str:
    about = f" about order {follow_up.order_id}" if follow_up.order_id else ""
    return f"Following up as promised{about}: {follow_up.note}"


class Scheduler:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        clock: Clock,
        *,
        on_fire: Callable[[FiredFollowUp], None] | None = None,
    ) -> None:
        self.sessions = sessions
        self.clock = clock
        self.on_fire = on_fire

    def run_due(self, *, limit: int = 50) -> list[FiredFollowUp]:
        """Fire every follow-up due now (up to `limit`). Safe to call from many workers."""
        now = self.clock.now()
        fired: list[FiredFollowUp] = []
        with self.sessions.begin() as db:
            rows = db.scalars(
                select(FollowUpRow)
                .where(FollowUpRow.status == FollowUpStatus.SCHEDULED, FollowUpRow.due_at <= now)
                .order_by(FollowUpRow.due_at, FollowUpRow.follow_up_id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            ).all()
            log = EventLog(db)
            for row in rows:
                row.status = FollowUpStatus.FIRED
                row.fired_at = now
                item = FiredFollowUp(
                    follow_up_id=row.follow_up_id,
                    conversation_id=row.conversation_id,
                    order_id=row.order_id,
                    due_at=row.due_at,
                    fired_at=now,
                    note=row.note,
                )
                log.append(
                    row.conversation_id,
                    EventType.FOLLOW_UP_FIRED,
                    at=now,
                    payload={"follow_up_id": row.follow_up_id},
                )
                log.append(
                    row.conversation_id,
                    EventType.AGENT_MESSAGE,
                    at=now,
                    payload={"text": reminder_text(item)},
                )
                fired.append(item)
        for item in fired:  # after commit: hooks never see an un-fired row
            if self.on_fire:
                self.on_fire(item)
        return fired

    def pending(self) -> int:
        with self.sessions() as db:
            return len(
                db.scalars(
                    select(FollowUpRow.follow_up_id).where(
                        FollowUpRow.status == FollowUpStatus.SCHEDULED
                    )
                ).all()
            )


__all__ = ["FiredFollowUp", "Scheduler", "reminder_text"]
