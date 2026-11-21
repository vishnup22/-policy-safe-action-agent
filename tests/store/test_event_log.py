from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from psa.domain import EventType
from psa.store import EventLog, UnknownConversationError, make_session_factory, transaction
from psa.store.models import EventRow
from tests.policy.helpers import NOW

pytestmark = pytest.mark.db


def _conversation(db: Session) -> tuple[EventLog, str]:
    log = EventLog(db)
    return log, log.start_conversation(at=NOW)


def test_sequences_are_gap_free_and_ordered(db: Session) -> None:
    log, conv = _conversation(db)
    for i in range(5):
        log.append(conv, EventType.USER_MESSAGE, at=NOW + timedelta(seconds=i), payload={"i": i})
    events = log.read(conv)
    assert [e.seq for e in events] == list(range(6))
    assert events[0].type is EventType.CONVERSATION_STARTED
    assert [e.payload.get("i") for e in events[1:]] == [0, 1, 2, 3, 4]


def test_sequences_are_per_conversation(db: Session) -> None:
    log = EventLog(db)
    a, b = log.start_conversation(at=NOW), log.start_conversation(at=NOW)
    log.append(a, EventType.USER_MESSAGE, at=NOW)
    log.append(b, EventType.USER_MESSAGE, at=NOW)
    assert [e.seq for e in log.read(a)] == [0, 1]
    assert [e.seq for e in log.read(b)] == [0, 1]


def test_policy_version_required_in_code(db: Session) -> None:
    log, conv = _conversation(db)
    with pytest.raises(ValueError, match="policy version"):
        log.append(conv, EventType.POLICY_DECISION, at=NOW, payload={})
    event = log.append(conv, EventType.POLICY_DECISION, at=NOW, policy_version="2026.11.21-1")
    assert event.policy_version == "2026.11.21-1"


def test_policy_version_required_in_database(db: Session) -> None:
    _, conv = _conversation(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            EventRow(
                event_id="evt_rawinsert",
                conversation_id=conv,
                seq=99,
                type=EventType.ACTION_EXECUTED,
                at=NOW,
                policy_version=None,
                payload={},
            )
        )
        db.flush()


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param(lambda: update(EventRow).values(payload={"tampered": True}), id="update"),
        pytest.param(lambda: delete(EventRow), id="delete"),
        pytest.param(lambda: text("TRUNCATE events CASCADE"), id="truncate"),
    ],
)
def test_events_are_append_only_in_database(db: Session, statement: object) -> None:
    log, conv = _conversation(db)
    log.append(conv, EventType.USER_MESSAGE, at=NOW, payload={"text": "hi"})
    with pytest.raises(DBAPIError, match="append-only"), db.begin_nested():
        db.execute(statement())  # type: ignore[operator]
    assert len(log.read(conv)) == 2


def test_duplicate_seq_rejected(db: Session) -> None:
    _, conv = _conversation(db)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            EventRow(
                event_id="evt_duplicate",
                conversation_id=conv,
                seq=0,
                type=EventType.USER_MESSAGE,
                at=NOW,
                payload={},
            )
        )
        db.flush()


def test_rolled_back_append_leaves_no_gap(db: Session) -> None:
    log, conv = _conversation(db)
    with pytest.raises(RuntimeError), db.begin_nested():
        log.append(conv, EventType.USER_MESSAGE, at=NOW, payload={"lost": True})
        raise RuntimeError("simulated failure after append")
    log.append(conv, EventType.USER_MESSAGE, at=NOW, payload={"kept": True})
    events = log.read(conv)
    assert [e.seq for e in events] == [0, 1]
    assert events[1].payload == {"kept": True}


def test_unknown_conversation_rejected(db: Session) -> None:
    with pytest.raises(UnknownConversationError):
        EventLog(db).append("conv_doesnotexist", EventType.USER_MESSAGE, at=NOW)


def test_concurrent_appends_stay_gap_free(pg_engine: Engine) -> None:
    factory = make_session_factory(pg_engine)
    with transaction(factory) as session:
        conv = EventLog(session).start_conversation(at=NOW)

    workers, per_worker = 8, 25

    def worker(n: int) -> None:
        for i in range(per_worker):
            with transaction(factory) as session:
                EventLog(session).append(
                    conv, EventType.TOOL_CALL, at=NOW, payload={"worker": n, "i": i}
                )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(worker, range(workers)))

    with factory() as session:
        seqs = list(
            session.scalars(
                select(EventRow.seq).where(EventRow.conversation_id == conv).order_by(EventRow.seq)
            )
        )
    assert seqs == list(range(workers * per_worker + 1))
