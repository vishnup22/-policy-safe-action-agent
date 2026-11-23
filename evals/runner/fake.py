"""An explicitly non-agent echo runtime for offline harness smoke checks."""

from collections.abc import Sequence

from sqlalchemy.orm import Session, sessionmaker

from evals.schema import Scenario
from psa.clock import Clock
from psa.domain import EventType
from psa.runtime.ports import (
    ApprovalResolution,
    RuntimeConfig,
    SessionStart,
    SimulatorTurn,
    TurnResult,
)
from psa.store import EventLog
from psa.store.models import ConversationRow


class EchoRuntime:
    def __init__(self, config: RuntimeConfig, *, sessions: sessionmaker[Session], clock: Clock):
        self._config, self.sessions, self.clock = config, sessions, clock

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    def start_conversation(self, session: SessionStart) -> str:
        with self.sessions.begin() as db:
            identifier = EventLog(db).start_conversation(
                at=self.clock.now(), customer_id=session.customer_id
            )
            row = db.get(ConversationRow, identifier)
            assert row is not None
            row.identity_verified = session.identity_verified
            return identifier

    def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
        reply = f"echo: {text}"
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
                    payload={"text": reply},
                ),
            )
        return TurnResult(conversation_id=conversation_id, reply_text=reply, events=events)

    def resolve_approval(
        self,
        approval_id: str,
        resolution: ApprovalResolution,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> TurnResult:
        raise LookupError("Echo runtime never requests approvals")

    def set_policy_version(self, version: str) -> None:
        self._config = self._config.model_copy(update={"policy_version": version})


class StopSimulator:
    def next_message(self, scenario: Scenario, transcript: Sequence[SimulatorTurn]) -> str | None:
        return None
