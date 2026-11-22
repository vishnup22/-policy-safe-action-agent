"""Independent fact state reconstructed from the initial world and committed effects."""

from datetime import datetime

from psa.domain import (
    ActionIntent,
    CancelOrderArgs,
    Customer,
    IssueRefundArgs,
    IssueStoreCreditArgs,
    Order,
    OrderStatus,
    UpdateAddressArgs,
)
from psa.seed import World


class WorldFacts:
    def __init__(self, world: World):
        self.orders = {o.order_id: o for o in world.orders}
        self.customers = {c.customer_id: c for c in world.customers}
        self.credits: list[tuple[str, int, datetime]] = []

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def get_customer(self, customer_id: str) -> Customer | None:
        return self.customers.get(customer_id)

    def store_credit_issued_cents(self, customer_id: str, since: datetime) -> int:
        return sum(
            amount
            for customer, amount, at in self.credits
            if customer == customer_id and at >= since
        )

    def apply(self, intent: ActionIntent, at: datetime) -> None:
        args = intent.args
        if isinstance(args, IssueStoreCreditArgs):
            self.credits.append((args.customer_id, args.amount_cents, at))
        if isinstance(args, (IssueRefundArgs, CancelOrderArgs, UpdateAddressArgs)):
            order = self.orders.get(args.order_id)
            if order is None:
                return
            if isinstance(args, IssueRefundArgs):
                refunded = order.amount_refunded_cents + args.amount_cents
                # Retain even invalid effects for independent subsequent judgments.
                self.orders[args.order_id] = order.model_copy(
                    update={
                        "amount_refunded_cents": refunded,
                        "status": OrderStatus.REFUNDED
                        if refunded >= order.amount_paid_cents
                        else OrderStatus.PARTIALLY_REFUNDED,
                    }
                )
            elif isinstance(args, CancelOrderArgs):
                self.orders[args.order_id] = order.model_copy(
                    update={"status": OrderStatus.CANCELLED}
                )
            else:
                self.orders[args.order_id] = order.model_copy(
                    update={"shipping_address": args.new_address}
                )
