"""Load a synthetic world in the caller's transaction; never silently overwrite data."""

from sqlalchemy.orm import Session

from psa.seed import World
from psa.store import CommerceRepo


def load_world(world: World, session: Session) -> None:
    repo = CommerceRepo(session)
    for customer in world.customers:
        repo.add_customer(customer)
    for order in world.orders:
        repo.add_order(order)
    for shipment in world.shipments:
        repo.add_shipment(shipment)
