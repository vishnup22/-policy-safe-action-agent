"""Composable edge-case builders. Every update is revalidated against the domain."""

from datetime import datetime, timedelta
from typing import Any

from psa.domain.commerce import ItemCategory, Order, OrderItem, OrderStatus
from psa.seed.world import synthetic_address


def replace_order(order: Order, **changes: Any) -> Order:
    return Order.model_validate({**order.model_dump(), **changes})


def delivered_days_ago(
    n: int,
    *,
    now: datetime,
    order_id: str = "ord_900001",
    customer_id: str = "cus_000001",
    amount_cents: int = 10000,
) -> Order:
    if n < 0 or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("days must be nonnegative and now timezone-aware")
    delivered = now - timedelta(days=n)
    return Order(
        order_id=order_id,
        customer_id=customer_id,
        status=OrderStatus.DELIVERED,
        items=(
            OrderItem(
                sku="LSG-0001",
                name="Synthetic boundary item",
                category=ItemCategory.APPAREL,
                quantity=1,
                unit_price_cents=amount_cents,
            ),
        ),
        amount_paid_cents=amount_cents,
        shipping_address=synthetic_address(),
        placed_at=delivered - timedelta(days=4),
        shipped_at=delivered - timedelta(days=3),
        delivered_at=delivered,
    )


def order_with_final_sale_item(*, now: datetime, order: Order | None = None) -> Order:
    order = order or delivered_days_ago(10, now=now)
    items = (order.items[0].model_copy(update={"final_sale": True}), *order.items[1:])
    return replace_order(order, items=items)


def refund_remaining_exactly(cents: int, *, now: datetime, order: Order | None = None) -> Order:
    order = order or delivered_days_ago(10, now=now, amount_cents=max(cents, 10000))
    if not 0 <= cents <= order.amount_paid_cents:
        raise ValueError("remaining refund must be between zero and paid amount")
    refunded = order.amount_paid_cents - cents
    status = (
        OrderStatus.REFUNDED
        if cents == 0
        else (OrderStatus.PARTIALLY_REFUNDED if refunded else OrderStatus.DELIVERED)
    )
    return replace_order(order, amount_refunded_cents=refunded, status=status)


def shipped_not_delivered(*, now: datetime, order: Order | None = None) -> Order:
    order = order or delivered_days_ago(0, now=now)
    return replace_order(order, status=OrderStatus.SHIPPED, delivered_at=None)


def owned_by_other_customer(
    *, now: datetime, order: Order | None = None, customer_id: str = "cus_000002"
) -> Order:
    return replace_order(order or delivered_days_ago(10, now=now), customer_id=customer_id)


def with_injected_note(text: str, *, now: datetime, order: Order | None = None) -> Order:
    return replace_order(order or delivered_days_ago(31, now=now), notes=text)
