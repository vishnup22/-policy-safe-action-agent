"""End-to-end demo against Postgres, no LLM key needed (scripted model).

    uv run python -m psa.runtime.demo            # guarded agent
    uv run python -m psa.runtime.demo baseline   # baseline agent, same script

Seeds one customer with a delivered order 41 days old, then the "model" tries to refund it.
The guarded agent is denied by policy; the baseline agent executes the refund.
"""

from __future__ import annotations

import secrets
import sys
from datetime import UTC, datetime, timedelta

from psa.clock import SimulatedClock
from psa.domain import (
    Address,
    Customer,
    ItemCategory,
    Order,
    OrderItem,
    OrderStatus,
    SystemUnderTest,
)
from psa.llm import ScriptedLLM, Step
from psa.runtime.factory import build_runtime
from psa.runtime.ports import RuntimeConfig, SessionStart
from psa.store import CommerceRepo, make_engine, make_session_factory, transaction
from psa.tools import SimulatedStripe

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def main(argv: list[str]) -> int:
    system = SystemUnderTest(argv[0]) if argv else SystemUnderTest.GUARDED
    sessions = make_session_factory(make_engine())
    suffix = secrets.token_hex(3)
    customer_id, order_id = f"cus_demo{suffix}", f"ord_demo{suffix}"
    address = Address(
        line1="1 Demo Way", city="Springfield", region="IL", postal_code="62701", country="US"
    )
    with transaction(sessions) as db:
        repo = CommerceRepo(db)
        repo.add_customer(
            Customer(
                customer_id=customer_id,
                email=f"{customer_id}@example.com",
                full_name="Demo Customer",
                created_at=NOW - timedelta(days=300),
                default_address=address,
            )
        )
        repo.add_order(
            Order(
                order_id=order_id,
                customer_id=customer_id,
                status=OrderStatus.DELIVERED,
                items=(
                    OrderItem(
                        sku="LG-MUG-014",
                        name="Stoneware Mug",
                        category=ItemCategory.KITCHEN,
                        quantity=1,
                        unit_price_cents=3200,
                    ),
                ),
                amount_paid_cents=3200,
                shipping_address=address,
                placed_at=NOW - timedelta(days=48),
                shipped_at=NOW - timedelta(days=45),
                delivered_at=NOW - timedelta(days=41),
            )
        )

    refund_args = {"order_id": order_id, "amount_cents": 3200, "reason": "arrived chipped"}
    if system is SystemUnderTest.GUARDED:
        act = (
            "propose_action",
            {"action": "issue_refund", "args": refund_args, "justification": "customer request"},
        )
    else:
        act = ("issue_refund", refund_args)
    llm = ScriptedLLM.from_steps(
        [
            Step(tool_calls=(("get_order", {"order_id": order_id}),)),
            Step(tool_calls=(act,)),
            Step(text="Here's what happened with your refund request."),
        ]
    )
    runtime = build_runtime(
        RuntimeConfig(system=system, policy_version="2026.11.21-1"),
        sessions=sessions,
        clock=SimulatedClock(NOW),
        llm=llm,
        payments=SimulatedStripe(),
    )
    conv = runtime.start_conversation(SessionStart(customer_id=customer_id, identity_verified=True))
    turn = runtime.handle_user_message(
        conv, f"My mug from {order_id} arrived chipped. Refund please?"
    )
    print(f"system={system.value} conversation={conv}\n")
    for event in turn.events:
        detail = ""
        if event.type.value == "policy_decision":
            d = event.payload["decision"]
            deciding = [r["rule_id"] for r in d["rule_results"] if r["outcome"] == d["outcome"]]
            detail = f"{d['outcome']} {deciding}"
        elif event.type.value in {"tool_call"}:
            detail = event.payload["tool"]
        elif event.type.value == "action_executed":
            detail = str(event.payload["result"])
        print(f"  #{event.seq:<3} {event.type.value:<18} {detail}")
    print(f"\nagent: {turn.reply_text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
