"""T6.3 exit criterion: a follow-up survives a process restart and fires exactly once."""

from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest
from sqlalchemy.orm import Session, sessionmaker

from psa.clock import SimulatedClock
from psa.domain import EventType
from psa.scheduler import FiredFollowUp, Scheduler, reminder_text
from psa.store import EventLog, make_session_factory
from psa.store.models import FollowUpRow, FollowUpStatus
from tests.store.conftest import SchemaFactory

pytestmark = pytest.mark.db

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def sessions(schemas: SchemaFactory) -> sessionmaker[Session]:
    # Real commits (not the rolled-back `db` fixture): restarts and concurrency need them.
    return make_session_factory(schemas.create())


def schedule(sessions: sessionmaker[Session], *, due_in: timedelta, note: str = "check in") -> str:
    with sessions.begin() as db:
        conversation = EventLog(db).start_conversation(at=NOW, customer_id=None)
        db.add(
            FollowUpRow(
                follow_up_id=f"fup_{conversation[-8:]}",
                conversation_id=conversation,
                order_id=None,
                due_at=NOW + due_in,
                note=note,
                status=FollowUpStatus.SCHEDULED,
            )
        )
    return conversation


def events(sessions: sessionmaker[Session], conversation: str) -> list[EventType]:
    with sessions() as db:
        return [e.type for e in EventLog(db).read(conversation)]


def test_not_due_yet_then_fires_once_after_restart(sessions: sessionmaker[Session]) -> None:
    conversation = schedule(sessions, due_in=timedelta(days=2), note="Your refund should land.")
    clock = SimulatedClock(NOW)
    assert Scheduler(sessions, clock).run_due() == []

    # "Restart": a brand-new scheduler (new process) with the clock past the due time.
    clock.advance(timedelta(days=2, minutes=1))
    seen: list[FiredFollowUp] = []
    fired = Scheduler(sessions, clock, on_fire=seen.append).run_due()
    assert [f.conversation_id for f in fired] == [conversation]
    assert seen == fired
    assert Scheduler(sessions, clock).run_due() == []  # never twice

    types = events(sessions, conversation)
    assert types.count(EventType.FOLLOW_UP_FIRED) == 1
    assert types[-2:] == [EventType.FOLLOW_UP_FIRED, EventType.AGENT_MESSAGE]
    with sessions() as db:
        last = EventLog(db).read(conversation)[-1]
        row = db.get(FollowUpRow, fired[0].follow_up_id)
        assert row is not None
        assert row.status is FollowUpStatus.FIRED
        assert row.fired_at == clock.now()
    assert last.payload["text"] == reminder_text(fired[0])
    assert "Your refund should land." in last.payload["text"]


def test_due_exactly_now_fires(sessions: sessionmaker[Session]) -> None:
    schedule(sessions, due_in=timedelta(hours=1))
    clock = SimulatedClock(NOW + timedelta(hours=1))
    assert len(Scheduler(sessions, clock).run_due()) == 1


def test_concurrent_workers_fire_each_follow_up_exactly_once(
    sessions: sessionmaker[Session],
) -> None:
    conversations = [schedule(sessions, due_in=timedelta(hours=1)) for _ in range(12)]
    clock = SimulatedClock(NOW + timedelta(hours=2))
    workers = 4
    barrier = Barrier(workers)
    results: list[list[FiredFollowUp]] = []

    def work() -> None:
        barrier.wait()
        results.append(Scheduler(sessions, clock).run_due(limit=5))

    threads = [Thread(target=work) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    while leftover := Scheduler(sessions, clock).run_due(limit=5):
        results.append(leftover)

    fired_ids = [f.follow_up_id for batch in results for f in batch]
    assert len(fired_ids) == len(set(fired_ids)) == 12
    for conversation in conversations:
        assert events(sessions, conversation).count(EventType.FOLLOW_UP_FIRED) == 1
    assert Scheduler(sessions, clock).pending() == 0
