"""AgentRuntime implementation shared by the baseline and guarded systems.

Each public call is ONE database transaction: the user message, every tool call, proposal,
decision and execution, the agent reply and the updated LLM transcript commit together.
The conversation row is locked for the turn, so turns of one conversation never interleave.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from psa.agent import BaselineAgent, GuardedAgent
from psa.agent.agents import _AgentBase
from psa.clock import Clock
from psa.domain import DecisionOutcome, EventType, SystemUnderTest
from psa.executor import Executor, resolve_approval
from psa.llm import LLMClient, LLMError
from psa.policy import PolicyRegistry, PolicySet, SessionContext, decide
from psa.runtime.ports import (
    ApprovalResolution,
    RuntimeConfig,
    SessionStart,
    TurnResult,
)
from psa.store import CommerceRepo, EventLog, UnknownConversationError, transaction
from psa.store.models import ConversationRow, LLMTranscriptRow
from psa.tools import FaultInjector, PaymentsGateway, ToolContext

LLM_ERROR_REPLY = (
    "I'm sorry, I'm having trouble right now. Please try again in a moment, or I can connect "
    "you with a team member."
)


class PolicySafeRuntime:
    def __init__(
        self,
        config: RuntimeConfig,
        *,
        sessions: sessionmaker[Session],
        clock: Clock,
        llm: LLMClient,
        payments: PaymentsGateway,
        registry: PolicyRegistry,
        executor: Executor | None = None,
    ) -> None:
        self._config = config
        self._sessions = sessions
        self._clock = clock
        self._llm = llm
        self._payments = payments
        self._registry = registry
        self._executor = executor or Executor(clock)
        self._faults = FaultInjector(config.faults)
        registry.get(config.policy_set, config.policy_version)  # fail fast on bad version

    # ------------------------------------------------------------------ AgentRuntime

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    def set_policy_version(self, version: str) -> None:
        self._registry.get(self._config.policy_set, version)
        self._config = self._config.model_copy(update={"policy_version": version})

    def start_conversation(self, session: SessionStart) -> str:
        if session.identity_verified and session.customer_id is None:
            raise ValueError("a verified session needs a customer_id")
        with transaction(self._sessions) as db:
            conversation_id = EventLog(db).start_conversation(
                at=self._clock.now(), customer_id=session.customer_id
            )
            row = db.get(ConversationRow, conversation_id)
            assert row is not None
            row.identity_verified = session.identity_verified
            db.add(
                LLMTranscriptRow(
                    conversation_id=conversation_id,
                    provider=self._llm.provider,
                    model=self._llm.model,
                    messages=[],
                    updated_at=self._clock.now(),
                )
            )
        return conversation_id

    def handle_user_message(self, conversation_id: str, text: str) -> TurnResult:
        with transaction(self._sessions) as db:
            row, transcript_row, log, first_seq = self._open(db, conversation_id)
            log.append(
                conversation_id,
                EventType.USER_MESSAGE,
                at=self._clock.now(),
                payload={"text": text},
            )
            agent = self._agent(db, log, row)
            transcript = [*transcript_row.messages, self._llm.user_message(text)]
            pending: str | None = None
            try:
                outcome = agent.run(transcript)
                transcript, reply = outcome.state["transcript"], outcome.state["reply"]
                pending = outcome.pending_approval_id
            except LLMError:
                reply = LLM_ERROR_REPLY
            log.append(
                conversation_id,
                EventType.AGENT_MESSAGE,
                at=self._clock.now(),
                payload={"text": reply},
            )
            self._save_transcript(transcript_row, transcript)
            events = [e for e in log.read(conversation_id) if e.seq >= first_seq]
        return TurnResult(
            conversation_id=conversation_id,
            reply_text=reply,
            events=tuple(events),
            pending_approval_id=pending,
        )

    def resolve_approval(
        self,
        approval_id: str,
        resolution: ApprovalResolution,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> TurnResult:
        with transaction(self._sessions) as db:
            log = EventLog(db)
            resolved = resolve_approval(
                db, log, self._clock, approval_id, resolution, reviewer=reviewer, note=note
            )
            conversation_id = resolved.conversation_id
            row, transcript_row, _, first_seq = self._open(db, conversation_id)
            first_seq -= 1  # include the APPROVAL_RESOLVED event appended above
            reply = self._apply_resolution(db, log, row, resolved)
            log.append(
                conversation_id,
                EventType.AGENT_MESSAGE,
                at=self._clock.now(),
                payload={"text": reply},
            )
            note_msg = self._llm.user_message(
                f"[Support system update, not from the customer] {reply}"
            )
            self._save_transcript(transcript_row, [*transcript_row.messages, note_msg])
            events = [e for e in log.read(conversation_id) if e.seq >= first_seq]
        return TurnResult(conversation_id=conversation_id, reply_text=reply, events=tuple(events))

    # ------------------------------------------------------------------ internals

    def _policy(self) -> PolicySet:
        return self._registry.get(self._config.policy_set, self._config.policy_version)

    def _open(
        self, db: Session, conversation_id: str
    ) -> tuple[ConversationRow, LLMTranscriptRow, EventLog, int]:
        row = db.get(ConversationRow, conversation_id, with_for_update=True)
        transcript_row = db.get(LLMTranscriptRow, conversation_id)
        if row is None or transcript_row is None:
            raise UnknownConversationError(conversation_id)
        return row, transcript_row, EventLog(db), row.next_seq

    def _tool_context(self, db: Session, row: ConversationRow) -> ToolContext:
        session = SessionContext(
            conversation_id=row.conversation_id,
            customer_id=row.customer_id,
            identity_verified=row.identity_verified,
        )
        return ToolContext(
            db=db,
            clock=self._clock,
            session=session,
            policy=self._policy(),
            payments=self._payments,
            faults=self._faults,
        )

    def _agent(self, db: Session, log: EventLog, row: ConversationRow) -> _AgentBase:
        cls = GuardedAgent if self._config.system is SystemUnderTest.GUARDED else BaselineAgent
        return cls(
            llm=self._llm,
            ctx=self._tool_context(db, row),
            log=log,
            executor=self._executor,
            policy=self._policy(),
            max_steps=self._config.max_agent_steps,
        )

    def _apply_resolution(self, db: Session, log: EventLog, row: ConversationRow, resolved) -> str:  # type: ignore[no-untyped-def]
        if resolved.resolution is ApprovalResolution.REJECTED:
            return "A team member reviewed your request and wasn't able to approve it."
        # Re-check policy at execution time: approval overrides only the approval requirement.
        ctx = self._tool_context(db, row)
        policy = self._policy()
        decision = decide(
            resolved.intent, policy, session=ctx.session, source=CommerceRepo(db), clock=self._clock
        )
        log.append(
            row.conversation_id,
            EventType.POLICY_DECISION,
            at=self._clock.now(),
            policy_version=decision.policy_version,
            payload={"decision": decision.model_dump(mode="json")},
        )
        if decision.outcome not in (DecisionOutcome.ALLOW, DecisionOutcome.REQUIRE_APPROVAL):
            return (
                "Your request was approved, but it no longer meets store policy, "
                "so it wasn't processed."
            )
        result = self._executor.execute(
            resolved.intent, ctx=ctx, log=log, policy_version=policy.version
        )
        if result.status.value == "failed":
            return f"Your request was approved, but processing failed: {result.error}"
        return "Good news: a team member approved your request and it has been processed."

    def _save_transcript(self, row: LLMTranscriptRow, transcript: list[dict[str, object]]) -> None:
        row.messages = list(transcript)
        row.updated_at = self._clock.now()
