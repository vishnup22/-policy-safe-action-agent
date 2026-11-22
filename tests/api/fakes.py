"""Reference FakeRuntime with persistence only, no production runtime imports."""

from sqlalchemy.orm import Session, sessionmaker
from tests.runtime.test_ports import FakeRuntime

from psa.clock import Clock
from psa.domain import EventType
from psa.runtime.ports import ApprovalResolution, RuntimeConfig, SessionStart, TurnResult
from psa.store import EventLog
from psa.store.models import ApprovalRow, ApprovalStatus, ConversationRow


class PersistedFake(FakeRuntime):
    def __init__(self, config: RuntimeConfig, *, sessions: sessionmaker[Session], clock: Clock):
        super().__init__(config)
        self.sessions, self.clock = sessions, clock
        self.started: list[SessionStart] = []

    def start_conversation(self, session: SessionStart) -> str:
        identifier = super().start_conversation(session)
        self.started.append(session)
        with self.sessions.begin() as db:
            EventLog(db).start_conversation(
                at=self.clock.now(), customer_id=session.customer_id, conversation_id=identifier
            )
            row = db.get(ConversationRow, identifier)
            assert row is not None
            row.identity_verified = session.identity_verified
        return identifier

    def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
        turn = super().handle_user_message(conversation_id, text)
        with self.sessions.begin() as db:
            log = EventLog(db)
            events = (
                log.append(
                    conversation_id,
                    EventType.USER_MESSAGE,
                    at=self.clock.now(),
                    payload={"text": text},
                ),
                log.append(
                    conversation_id,
                    EventType.AGENT_MESSAGE,
                    at=self.clock.now(),
                    payload={"text": turn.reply_text},
                ),
            )
        return turn.model_copy(update={"events": events})

    def resolve_approval(
        self,
        approval_id: str,
        resolution: ApprovalResolution,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> TurnResult:
        turn = super().resolve_approval(approval_id, resolution, reviewer=reviewer, note=note)
        with self.sessions.begin() as db:
            row = db.get(ApprovalRow, approval_id)
            assert row is not None
            if row.status != ApprovalStatus.PENDING:
                raise ValueError("already resolved")
            row.status = ApprovalStatus(resolution.value)
            row.resolved_at = self.clock.now()
            row.reviewer = reviewer
            row.note = note
        return turn
