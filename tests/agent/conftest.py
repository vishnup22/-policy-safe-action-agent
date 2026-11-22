"""Fixtures for end-to-end agent tests: a migrated Postgres schema and a tiny shop."""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from psa.clock import SimulatedClock
from psa.domain import Event, EventType, OrderItem, SystemUnderTest
from psa.llm import ScriptedLLM, Step
from psa.runtime.factory import build_runtime, default_registry
from psa.runtime.ports import AgentRuntime, RuntimeConfig, SessionStart, ToolFault
from psa.store import CommerceRepo, EventLog, make_session_factory, transaction
from psa.store.models import RefundRow
from psa.tools import SimulatedStripe
from tests.policy.helpers import NOW, customer, item, order
from tests.store.conftest import pg_engine, schemas  # noqa: F401  (re-exported fixtures)

pytestmark = pytest.mark.db
V1 = "2026.11.21-1"


@pytest.fixture
def sessions(pg_engine: Engine) -> sessionmaker[Session]:  # noqa: F811
    return make_session_factory(pg_engine)


@dataclass
class Shop:
    sessions: sessionmaker[Session]
    me: str = field(default_factory=lambda: f"cus_{secrets.token_hex(4)}")
    someone_else: str = field(default_factory=lambda: f"cus_{secrets.token_hex(4)}")

    def __post_init__(self) -> None:
        with transaction(self.sessions) as db:
            repo = CommerceRepo(db)
            repo.add_customer(
                customer(self.me).model_copy(update={"email": f"{self.me}@example.com"})
            )
            repo.add_customer(
                customer(self.someone_else).model_copy(
                    update={"email": f"{self.someone_else}@example.com"}
                )
            )

    def order(
        self,
        *,
        owner: str | None = None,
        items: tuple[OrderItem, ...] | None = None,
        delivered_days_ago: int | None = 10,
        notes: str | None = None,
        **kwargs: Any,
    ) -> str:
        order_id = f"ord_{secrets.token_hex(5)}"
        o = order(
            order_id,
            customer_id=owner or self.me,
            items=items,
            delivered_ago=timedelta(days=delivered_days_ago)
            if delivered_days_ago is not None
            else None,
            **kwargs,
        )
        if notes:
            o = o.model_copy(update={"notes": notes})
        with transaction(self.sessions) as db:
            CommerceRepo(db).add_order(o)
        return order_id

    def refunds(self, order_id: str) -> int:
        with self.sessions() as db:
            return int(db.scalar(select(func.count()).where(RefundRow.order_id == order_id)) or 0)

    def refunded_cents(self, order_id: str) -> int:
        with self.sessions() as db:
            o = CommerceRepo(db).get_order(order_id)
            assert o is not None
            return o.amount_refunded_cents

    def events(self, conversation_id: str) -> list[Event]:
        with self.sessions() as db:
            return EventLog(db).read(conversation_id)


@pytest.fixture
def shop(sessions: sessionmaker[Session]) -> Shop:
    return Shop(sessions)


@dataclass
class Harness:
    runtime: AgentRuntime
    llm: ScriptedLLM
    payments: SimulatedStripe
    clock: SimulatedClock
    conversation_id: str


def harness(
    shop: Shop,
    system: SystemUnderTest,
    steps: Sequence[Step],
    *,
    customer_id: str | None = "me",
    verified: bool = True,
    faults: Sequence[ToolFault] = (),
    policy_version: str = V1,
    max_steps: int = 12,
) -> Harness:
    llm = ScriptedLLM.from_steps(steps)
    payments = SimulatedStripe()
    clock = SimulatedClock(NOW)
    runtime = build_runtime(
        RuntimeConfig(
            system=system,
            policy_version=policy_version,
            faults=tuple(faults),
            max_agent_steps=max_steps,
        ),
        sessions=shop.sessions,
        clock=clock,
        llm=llm,
        payments=payments,
        registry=default_registry(),
    )
    cid = shop.me if customer_id == "me" else customer_id
    conversation_id = runtime.start_conversation(
        SessionStart(customer_id=cid, identity_verified=verified and cid is not None)
    )
    return Harness(runtime, llm, payments, clock, conversation_id)


def propose(action: str, **args: Any) -> Step:
    return Step(
        tool_calls=(("propose_action", {"action": action, "args": args, "justification": "asked"}),)
    )


def direct(action: str, **args: Any) -> Step:
    return Step(tool_calls=((action, args),))


def of_type(events: Sequence[Event], kind: EventType) -> list[Event]:
    return [e for e in events if e.type is kind]


def last_tool_result(events: Sequence[Event]) -> dict[str, Any]:
    results = of_type(events, EventType.TOOL_RESULT)
    assert results, "no tool result recorded"
    return results[-1].payload


__all__ = [
    "V1",
    "Harness",
    "Shop",
    "direct",
    "harness",
    "item",
    "last_tool_result",
    "of_type",
    "propose",
]
