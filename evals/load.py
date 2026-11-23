"""Run a local API load check with an echo runtime and disposable Postgres schema."""

import argparse
import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from itertools import product
from threading import Barrier, Lock
from time import perf_counter
from typing import Any, Protocol

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from evals.metrics import percentile
from evals.runner.database import trial_database
from evals.runner.fake import EchoRuntime
from psa.api import Settings, create_app
from psa.clock import SimulatedClock
from psa.domain import ActionIntent, Decision, DecisionOutcome, EventType, IssueRefundArgs
from psa.executor.approvals import request_approval, resolve_approval
from psa.runtime.ports import ApprovalResolution, TurnResult
from psa.store import EventLog, database_url, new_id


class Response(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def text(self) -> str: ...

    def json(self) -> Any: ...


class LoadRuntime(EchoRuntime):
    def resolve_approval(
        self,
        approval_id: str,
        resolution: ApprovalResolution,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> TurnResult:
        with self.sessions.begin() as db:
            reviewed = resolve_approval(
                db, EventLog(db), self.clock, approval_id, resolution, reviewer=reviewer, note=note
            )
        return TurnResult(conversation_id=reviewed.conversation_id, reply_text="Review recorded.")


@dataclass(frozen=True)
class LoadResult:
    conversations: int
    turns_per_conversation: int
    requests: int
    p95_latency_ms: float
    approval_statuses: tuple[int, ...]


def seed_approval(
    sessions: sessionmaker[Session], clock: SimulatedClock, settings: Settings
) -> tuple[str, str]:
    at = clock.now()
    with sessions.begin() as db:
        log = EventLog(db)
        conversation = log.start_conversation(at=at)
        intent = ActionIntent(
            intent_id=new_id("int"),
            conversation_id=conversation,
            customer_id=None,
            args=IssueRefundArgs(
                order_id="ord_loadtest", amount_cents=30000, reason="Load fixture"
            ),
            justification="Test operator concurrency",
            proposed_at=at,
            idempotency_key=new_id("idem"),
        )
        decision = Decision(
            intent_id=intent.intent_id,
            outcome=DecisionOutcome.REQUIRE_APPROVAL,
            rule_results=(),
            policy_set=settings.policy_set,
            policy_version=settings.policy_version,
            evaluated_at=at,
            facts_snapshot={},
        )
        approval = request_approval(db, log, clock, intent, decision)
    return conversation, approval


def require_status(response: Response, status: int) -> Response:
    if response.status_code != status:
        raise RuntimeError(f"Expected HTTP {status}, got {response.status_code}: {response.text}")
    return response


def run_load(
    sessions: sessionmaker[Session], *, conversations: int, turns: int, workers: int
) -> LoadResult:
    if min(conversations, turns, workers) < 1:
        raise ValueError("conversations, turns, and workers must be positive")

    clock = SimulatedClock(datetime(2026, 11, 21, 12, tzinfo=UTC))
    settings = Settings(
        demo_passcode=SecretStr("load-passcode"),
        app_auth_secret=SecretStr(secrets.token_urlsafe(32)),
    )
    approval_conversation, approval = seed_approval(sessions, clock, settings)
    app = create_app(runtime_factory=LoadRuntime, sessions=sessions, clock=clock, settings=settings)
    samples: list[float] = []
    sample_lock = Lock()
    barrier = Barrier(2)

    with TestClient(app) as client:
        login = require_status(
            client.post("/api/auth/demo-login", json={"passcode": "load-passcode"}), 200
        )
        client.headers["Authorization"] = "Bearer " + login.json()["token"]

        def request(method: str, path: str, body: dict[str, str] | None = None) -> Response:
            started = perf_counter()
            response = client.request(method, path, json=body)
            elapsed = (perf_counter() - started) * 1000
            with sample_lock:
                samples.append(elapsed)
            return response

        def start(_: int) -> str:
            response = require_status(request("POST", "/api/conversations", {}), 201)
            return response.json()["conversation_id"]

        def send(work: tuple[str, int]) -> None:
            conversation, turn = work
            text = f"Synthetic turn {turn}"
            response = require_status(
                request("POST", f"/api/conversations/{conversation}/messages", {"text": text}), 200
            )
            if response.json()["reply"]["text"] != f"echo: {text}":
                raise RuntimeError(f"Unexpected reply for {conversation}")

        def check_sequence(conversation: str) -> None:
            response = require_status(
                request("GET", f"/api/conversations/{conversation}/events"), 200
            )
            sequences = [event["seq"] for event in response.json()["events"]]
            if sequences != list(range(1 + 2 * turns)):
                raise RuntimeError(
                    f"Missing or duplicate event sequence in {conversation}: {sequences}"
                )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            opened = list(pool.map(start, range(conversations)))
            if len(set(opened)) != conversations:
                raise RuntimeError("Conversation creation returned duplicate IDs")
            list(pool.map(send, product(opened, range(turns))))
            list(pool.map(check_sequence, opened))

        def review(_: int) -> int:
            barrier.wait(timeout=10)
            return request(
                "POST", f"/api/approvals/{approval}/resolve", {"resolution": "rejected"}
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = tuple(sorted(pool.map(review, range(2))))
        if statuses != (200, 409):
            raise RuntimeError(f"Expected one approval resolution and one conflict, got {statuses}")

    with sessions() as db:
        events = EventLog(db).read(approval_conversation)
    if sum(event.type == EventType.APPROVAL_RESOLVED for event in events) != 1:
        raise RuntimeError("Expected exactly one durable approval resolution")

    return LoadResult(conversations, turns, len(samples), percentile(samples, 0.95), statuses)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversations", type=int, default=16)
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if min(args.conversations, args.turns, args.workers) < 1:
        parser.error("conversations, turns, and workers must be positive")
    with trial_database(database_url()) as sessions:
        result = run_load(
            sessions, conversations=args.conversations, turns=args.turns, workers=args.workers
        )
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
