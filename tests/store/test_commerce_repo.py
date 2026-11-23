from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from psa.clock import SimulatedClock
from psa.domain import DecisionOutcome, ItemCategory, ReasonCode, Shipment, ShipmentStatus
from psa.policy import decide
from psa.store import CommerceRepo
from psa.store.models import OrderRow
from tests.policy.helpers import ALICE, BOB, NOW, V1, customer, item, order, refund, session

pytestmark = pytest.mark.db
DAY = timedelta(days=1)


def _seed(db: Session) -> CommerceRepo:
    repo = CommerceRepo(db)
    repo.add_customer(customer(ALICE))
    repo.add_customer(customer(BOB))
    return repo


def test_order_roundtrip_preserves_domain_model(db: Session) -> None:
    repo = _seed(db)
    original = order(
        items=(
            item("LG-TEE-001", 2000, quantity=2),
            item("LG-SALE-009", 1500, final_sale=True),
            item("LG-GIFT-050", 5000, category=ItemCategory.GIFT_CARD),
        ),
        refunded=500,
    )
    repo.add_order(original)
    db.expire_all()
    assert repo.get_order(original.order_id) == original


def test_customer_roundtrip_and_lookup_by_email(db: Session) -> None:
    repo = _seed(db)
    assert repo.get_customer(ALICE) == customer(ALICE)
    assert repo.find_customer_by_email(f"{BOB}@example.com") == customer(BOB)
    assert repo.get_customer("cus_nobody00") is None
    assert repo.find_customer_by_email("nobody@example.com") is None


def test_missing_order_is_none(db: Session) -> None:
    assert CommerceRepo(db).get_order("ord_missing1") is None


def test_orders_for_customer_sorted_by_placed_at(db: Session) -> None:
    repo = _seed(db)
    repo.add_order(order("ord_newer01", delivered_ago=2 * DAY))
    repo.add_order(order("ord_older01", delivered_ago=20 * DAY))
    repo.add_order(order("ord_bobs001", customer_id=BOB))
    assert [o.order_id for o in repo.orders_for_customer(ALICE)] == ["ord_older01", "ord_newer01"]


def test_shipments(db: Session) -> None:
    repo = _seed(db)
    o = order()
    repo.add_order(o)
    shipment = Shipment(
        shipment_id="shp_000001",
        order_id=o.order_id,
        carrier="Parcelway",
        tracking_number="PW123456789",
        status=ShipmentStatus.DELIVERED,
        shipped_at=o.shipped_at,
        delivered_at=o.delivered_at,
    )
    repo.add_shipment(shipment)
    assert repo.shipments_for_order(o.order_id) == [shipment]


def test_store_credit_window_sum(db: Session) -> None:
    repo = _seed(db)
    for n, (who, ago, cents) in enumerate(
        [(ALICE, 2 * DAY, 3000), (ALICE, 29 * DAY, 2000), (ALICE, 31 * DAY, 9000), (BOB, DAY, 7000)]
    ):
        repo.add_store_credit(
            credit_id=f"crd_{n:06d}",
            customer_id=who,
            amount_cents=cents,
            issued_at=NOW - ago,
            idempotency_key=f"idem_credit_{n}",
            intent_id=f"int_credit{n:04d}",
            reason="goodwill",
        )
    assert repo.store_credit_issued_cents(ALICE, NOW - 30 * DAY) == 5000
    assert repo.store_credit_issued_cents(BOB, NOW - 30 * DAY) == 7000
    assert repo.store_credit_issued_cents("cus_nobody00", NOW - 30 * DAY) == 0


def test_database_rejects_refund_above_paid(db: Session) -> None:
    repo = _seed(db)
    o = order()
    repo.add_order(o)
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            update(OrderRow)
            .where(OrderRow.order_id == o.order_id)
            .values(amount_refunded_cents=o.amount_paid_cents + 1)
        )


# ------------------------------------------------------------------ policy engine on real data


def _decide(db: Session, the_order_ago: timedelta, owner: str = ALICE) -> tuple[str, list[str]]:
    repo = _seed(db)
    repo.add_order(order(customer_id=owner, delivered_ago=the_order_ago))
    decision = decide(
        refund(),
        V1,
        session=session(),
        source=repo,
        clock=SimulatedClock(NOW),
    )
    return decision.outcome.value, [c.value for c in decision.reason_codes]


def test_policy_engine_reads_facts_from_postgres_allow(db: Session) -> None:
    assert _decide(db, 30 * DAY) == (DecisionOutcome.ALLOW.value, [])


def test_policy_engine_reads_facts_from_postgres_window(db: Session) -> None:
    assert _decide(db, 31 * DAY) == (
        DecisionOutcome.DENY.value,
        [ReasonCode.OUTSIDE_RETURN_WINDOW.value],
    )


def test_policy_engine_reads_facts_from_postgres_ownership(db: Session) -> None:
    assert _decide(db, 5 * DAY, owner=BOB) == (
        DecisionOutcome.DENY.value,
        [ReasonCode.ORDER_NOT_OWNED_BY_CUSTOMER.value],
    )
