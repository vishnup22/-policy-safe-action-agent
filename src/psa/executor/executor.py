"""Executes approved intents exactly once.

1. Claim the intent's idempotency key (INSERT ... ON CONFLICT DO NOTHING). A key that already
   succeeded returns the stored result: no second side effect, no second ACTION_EXECUTED.
2. Run the write tool inside a savepoint, so a failed attempt leaves no partial state.
3. Retry only retryable failures (timeout / 5xx / rate limit), never declines or bad input.
4. A per-tool circuit breaker fails fast after repeated failures.
5. Append ACTION_EXECUTED or ACTION_FAILED (with the policy version) to the event log.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from psa.clock import Clock
from psa.domain import ActionIntent, ActionName, EventType, ScheduleFollowUpArgs
from psa.store import EventLog
from psa.store.models import IdempotencyKeyRow, IdempotencyStatus
from psa.tools.context import ToolContext
from psa.tools.errors import ToolFailure
from psa.tools.write_tools import WRITE_TOOLS


class ExecutionStatus(StrEnum):
    EXECUTED = "executed"
    DUPLICATE = "duplicate"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error: str | None = None
    attempts: int = 0

    def for_model(self) -> dict[str, Any]:
        if self.status is ExecutionStatus.FAILED:
            return {"status": "failed", "error_code": self.error_code, "error": self.error}
        return {"status": self.status.value, "result": self.result}


@dataclass
class CircuitBreaker:
    clock: Clock
    threshold: int = 5
    cooldown: timedelta = timedelta(seconds=30)
    _failures: dict[str, int] = field(default_factory=dict[str, int])
    _opened_at: dict[str, Any] = field(default_factory=dict[str, Any])

    def allow(self, tool: str) -> bool:
        opened = self._opened_at.get(tool)
        if opened is None:
            return True
        if self.clock.now() - opened >= self.cooldown:
            del self._opened_at[tool]  # half-open: let one call through
            self._failures[tool] = self.threshold - 1
            return True
        return False

    def record(self, tool: str, *, ok: bool) -> None:
        if ok:
            self._failures.pop(tool, None)
            return
        self._failures[tool] = self._failures.get(tool, 0) + 1
        if self._failures[tool] >= self.threshold:
            self._opened_at[tool] = self.clock.now()


@dataclass
class Executor:
    clock: Clock
    max_attempts: int = 3
    backoff_s: float = 0.0
    sleep: Callable[[float], None] = lambda _s: None
    breaker: CircuitBreaker | None = None

    def __post_init__(self) -> None:
        if self.breaker is None:
            self.breaker = CircuitBreaker(self.clock)

    def execute(
        self, intent: ActionIntent, *, ctx: ToolContext, log: EventLog, policy_version: str
    ) -> ExecutionResult:
        db = ctx.db
        tool = intent.action.value
        now = self.clock.now()
        claimed = db.execute(
            insert(IdempotencyKeyRow)
            .values(
                key=intent.idempotency_key,
                intent_id=intent.intent_id,
                action=tool,
                status=IdempotencyStatus.IN_PROGRESS,
                result=None,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=["key"])
            .returning(IdempotencyKeyRow.key)
        ).scalar_one_or_none()
        if claimed is None:
            return self._existing(db, intent)

        breaker = self.breaker
        assert breaker is not None
        attempt = 0
        failure: ToolFailure | None = None
        while attempt < self.max_attempts:
            attempt += 1
            if not breaker.allow(tool):
                failure = ToolFailure("circuit_open", f"{tool} is temporarily unavailable")
                break
            try:
                with db.begin_nested():
                    ctx.faults.before_call(tool)
                    result = WRITE_TOOLS[intent.action](ctx, intent)
            except ToolFailure as exc:
                failure = exc
                breaker.record(tool, ok=False)
                log.append(
                    intent.conversation_id,
                    EventType.ACTION_FAILED,
                    at=self.clock.now(),
                    payload={
                        "intent_id": intent.intent_id,
                        "error": f"{exc.code}: {exc.message}",
                        "retryable": exc.retryable,
                        "attempt": attempt,
                    },
                )
                if not exc.retryable:
                    break
                self.sleep(self.backoff_s * attempt)
                continue
            breaker.record(tool, ok=True)
            self._finish(db, intent, IdempotencyStatus.SUCCEEDED, result)
            log.append(
                intent.conversation_id,
                EventType.ACTION_EXECUTED,
                at=self.clock.now(),
                policy_version=policy_version,
                payload={
                    "intent_id": intent.intent_id,
                    "idempotency_key": intent.idempotency_key,
                    "result": result,
                },
            )
            if intent.action is ActionName.SCHEDULE_FOLLOW_UP:
                args = intent.args
                assert isinstance(args, ScheduleFollowUpArgs)
                log.append(
                    intent.conversation_id,
                    EventType.FOLLOW_UP_SCHEDULED,
                    at=self.clock.now(),
                    payload={
                        "follow_up_id": result["follow_up_id"],
                        "due_at": result["due_at"],
                        "note": args.note,
                    },
                )
            return ExecutionResult(ExecutionStatus.EXECUTED, result=result, attempts=attempt)

        assert failure is not None
        self._finish(
            db,
            intent,
            IdempotencyStatus.FAILED,
            {"error_code": failure.code, "error": failure.message},
        )
        return ExecutionResult(
            ExecutionStatus.FAILED,
            error_code=failure.code,
            error=failure.message,
            attempts=attempt,
        )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _row(db: Session, key: str) -> IdempotencyKeyRow:
        return db.scalars(select(IdempotencyKeyRow).where(IdempotencyKeyRow.key == key)).one()

    def _finish(
        self, db: Session, intent: ActionIntent, status: IdempotencyStatus, result: dict[str, Any]
    ) -> None:
        row = self._row(db, intent.idempotency_key)
        row.status = status
        row.result = result
        row.updated_at = self.clock.now()
        db.flush()

    def _existing(self, db: Session, intent: ActionIntent) -> ExecutionResult:
        row = self._row(db, intent.idempotency_key)
        if row.status is IdempotencyStatus.SUCCEEDED:
            return ExecutionResult(ExecutionStatus.DUPLICATE, result=row.result)
        result = row.result or {}
        return ExecutionResult(
            ExecutionStatus.FAILED,
            error_code=str(result.get("error_code", "in_progress")),
            error=str(result.get("error", "this action is already being processed")),
        )
