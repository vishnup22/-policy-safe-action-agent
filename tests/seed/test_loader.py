"""Database round trips for the world loader."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from psa.seed import generate_world
from psa.seed.loader import load_world
from psa.store import CommerceRepo
from psa.store.models import CustomerRow, OrderRow, ShipmentRow


@pytest.mark.db
def test_load_world_roundtrip(db: Session) -> None:
    world = generate_world(42, datetime(2026, 11, 21, 12, tzinfo=UTC))
    load_world(world, db)
    assert db.scalar(select(func.count()).select_from(CustomerRow)) == 200
    assert db.scalar(select(func.count()).select_from(OrderRow)) == 600
    assert db.scalar(select(func.count()).select_from(ShipmentRow)) == len(world.shipments)
    repo = CommerceRepo(db)
    assert repo.get_customer(world.customers[0].customer_id) == world.customers[0]
    for order in (world.orders[0], world.orders[-1]):
        assert repo.get_order(order.order_id) == order
    shipment = world.shipments[0]
    assert repo.shipments_for_order(shipment.order_id) == [shipment]
