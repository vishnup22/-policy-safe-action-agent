"""Golden snapshot of v1 decisions. Any change in policy behavior shows up as a diff here.

Regenerate deliberately (and review the diff in the PR):
    UPDATE_GOLDEN=1 uv run pytest tests/policy/test_golden.py
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from psa.domain import Decision, ItemCategory, OrderStatus
from tests.policy.helpers import (
    ALICE,
    BOB,
    NOW,
    cancel,
    escalate,
    follow_up,
    item,
    order,
    refund,
    run,
    session,
    store_credit,
    ticket,
    update_address,
)

GOLDEN = Path(__file__).parent / "golden" / "decisions_v1.json"
DAY = timedelta(days=1)

CASES: dict[str, Callable[[], Decision]] = {
    "refund_in_window": lambda: run(refund(), order()),
    "refund_day_30": lambda: run(refund(), order(delivered_ago=30 * DAY)),
    "refund_day_31": lambda: run(refund(), order(delivered_ago=31 * DAY)),
    "refund_exactly_200": lambda: run(refund(20000), order(items=(item(price=25000),))),
    "refund_200_01": lambda: run(refund(20001), order(items=(item(price=25000),))),
    "refund_exceeds_refundable": lambda: run(
        refund(2201), order(status=OrderStatus.PARTIALLY_REFUNDED, refunded=1000)
    ),
    "refund_final_sale": lambda: run(refund(), order(items=(item(final_sale=True),))),
    "refund_gift_card": lambda: run(
        refund(5000), order(items=(item(price=5000, category=ItemCategory.GIFT_CARD),))
    ),
    "refund_not_delivered": lambda: run(
        refund(), order(status=OrderStatus.SHIPPED, delivered_ago=None)
    ),
    "refund_missing_delivery_time": lambda: run(refund(), order(delivered_ago=None)),
    "refund_unverified": lambda: run(refund(), order(), sess=session(verified=False)),
    "refund_other_customer": lambda: run(refund(), order(customer_id=BOB)),
    "refund_unknown_order": lambda: run(refund(order_id="ord_missing1")),
    "refund_multiple_violations": lambda: run(
        refund(30000),
        order(items=(item(price=25000, final_sale=True),), delivered_ago=45 * DAY),
        sess=session(verified=False),
    ),
    "store_credit_small": lambda: run(store_credit(2000)),
    "store_credit_needs_approval": lambda: run(store_credit(5001)),
    "store_credit_over_cap": lambda: run(
        store_credit(5000), credits=[(ALICE, NOW - 2 * DAY, 12000)]
    ),
    "cancel_unshipped": lambda: run(cancel(), order(status=OrderStatus.PAID, delivered_ago=None)),
    "cancel_shipped": lambda: run(cancel(), order(status=OrderStatus.SHIPPED, delivered_ago=None)),
    "cancel_cancelled": lambda: run(
        cancel(), order(status=OrderStatus.CANCELLED, delivered_ago=None)
    ),
    "address_ok": lambda: run(update_address(), order(status=OrderStatus.PAID, delivered_ago=None)),
    "address_other_country": lambda: run(
        update_address("CA"), order(status=OrderStatus.PAID, delivered_ago=None)
    ),
    "address_shipped": lambda: run(
        update_address(), order(status=OrderStatus.SHIPPED, delivered_ago=None)
    ),
    "ticket_anonymous": lambda: run(ticket(), sess=session(verified=False, customer_id=None)),
    "escalate_anonymous": lambda: run(escalate(), sess=session(verified=False, customer_id=None)),
    "follow_up_own_order": lambda: run(follow_up(), order()),
}


def _snapshot(decision: Decision) -> dict[str, object]:
    return {
        "outcome": decision.outcome.value,
        "policy_version": decision.policy_version,
        "rules": [
            [r.rule_id, r.outcome.value, r.reason_code.value if r.reason_code else None]
            for r in decision.rule_results
        ],
        "facts": decision.facts_snapshot,
    }


def test_golden_decisions_v1() -> None:
    actual = {name: _snapshot(build()) for name, build in CASES.items()}
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(
            json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert actual.keys() == expected.keys()
    for name in CASES:
        assert actual[name] == expected[name], f"golden mismatch for case '{name}'"
