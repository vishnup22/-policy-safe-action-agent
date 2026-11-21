"""Builders for policy tests. Everything is synthetic and pinned to NOW."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from psa.clock import SimulatedClock
from psa.domain import (
    ActionArgs,
    ActionIntent,
    Address,
    CancelOrderArgs,
    CreateTicketArgs,
    Customer,
    CustomerTier,
    Decision,
    EscalateToHumanArgs,
    IssueRefundArgs,
    IssueStoreCreditArgs,
    ItemCategory,
    Order,
    OrderItem,
    OrderStatus,
    ScheduleFollowUpArgs,
    UpdateAddressArgs,
)
from psa.policy import PolicyRegistry, SessionContext, decide

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
ALICE = "cus_alice01"
BOB = "cus_bobby02"
ORDER = "ord_000001"
POLICY_ROOT = Path(__file__).resolve().parents[2] / "policies"
REGISTRY = PolicyRegistry.from_dir(POLICY_ROOT)
V1 = REGISTRY.get("larkspur-returns", "2026.11.21-1")
V2 = REGISTRY.get("larkspur-returns", "2026.11.21-2")


def address(country: str = "US", line1: str = "12 Elm Street") -> Address:
    return Address(
        line1=line1, city="Springfield", region="IL", postal_code="62701", country=country
    )


def customer(customer_id: str = ALICE, tier: CustomerTier = CustomerTier.STANDARD) -> Customer:
    return Customer(
        customer_id=customer_id,
        email=f"{customer_id}@example.com",
        full_name="Test Customer",
        tier=tier,
        created_at=NOW - timedelta(days=400),
        default_address=address(),
    )


def item(
    sku: str = "LG-MUG-014",
    price: int = 3200,
    *,
    quantity: int = 1,
    category: ItemCategory = ItemCategory.KITCHEN,
    final_sale: bool = False,
) -> OrderItem:
    return OrderItem(
        sku=sku,
        name=f"Item {sku}",
        category=category,
        quantity=quantity,
        unit_price_cents=price,
        final_sale=final_sale,
    )


def order(
    order_id: str = ORDER,
    *,
    customer_id: str = ALICE,
    status: OrderStatus = OrderStatus.DELIVERED,
    items: tuple[OrderItem, ...] | None = None,
    delivered_ago: timedelta | None = timedelta(days=10),
    shipped: bool | None = None,
    refunded: int = 0,
    country: str = "US",
) -> Order:
    items = items if items is not None else (item(),)
    paid = sum(i.quantity * i.unit_price_cents for i in items)
    delivered_at = NOW - delivered_ago if delivered_ago is not None else None
    anchor = delivered_at if delivered_at is not None and delivered_at < NOW else NOW
    is_shipped = (
        shipped
        if shipped is not None
        else status
        not in {
            OrderStatus.PLACED,
            OrderStatus.PAID,
            OrderStatus.CANCELLED,
        }
    )
    return Order(
        order_id=order_id,
        customer_id=customer_id,
        status=status,
        items=items,
        amount_paid_cents=paid,
        amount_refunded_cents=refunded,
        shipping_address=address(country),
        placed_at=anchor - timedelta(days=5),
        shipped_at=anchor - timedelta(days=2) if is_shipped else None,
        delivered_at=delivered_at,
    )


@dataclass
class FakeSource:
    orders: dict[str, Order] = field(default_factory=dict[str, Order])
    customers: dict[str, Customer] = field(default_factory=dict[str, Customer])
    credits: list[tuple[str, datetime, int]] = field(
        default_factory=list[tuple[str, datetime, int]]
    )

    @classmethod
    def with_(
        cls, *orders: Order, credits: list[tuple[str, datetime, int]] | None = None
    ) -> FakeSource:
        return cls(
            orders={o.order_id: o for o in orders},
            customers={ALICE: customer(ALICE), BOB: customer(BOB)},
            credits=credits or [],
        )

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def get_customer(self, customer_id: str) -> Customer | None:
        return self.customers.get(customer_id)

    def store_credit_issued_cents(self, customer_id: str, since: datetime) -> int:
        return sum(c for who, at, c in self.credits if who == customer_id and at >= since)


def session(*, verified: bool = True, customer_id: str | None = ALICE) -> SessionContext:
    return SessionContext(
        conversation_id="conv_test", customer_id=customer_id, identity_verified=verified
    )


_counter = 0


def intent(args: ActionArgs, *, customer_id: str | None = ALICE) -> ActionIntent:
    global _counter
    _counter += 1
    return ActionIntent(
        intent_id=f"int_test{_counter:06d}",
        conversation_id="conv_test",
        customer_id=customer_id,
        args=args,
        justification="test",
        proposed_at=NOW,
        idempotency_key=f"idem_test{_counter:06d}",
    )


def refund(amount: int = 3200, order_id: str = ORDER, skus: tuple[str, ...] = ()) -> ActionIntent:
    return intent(
        IssueRefundArgs(order_id=order_id, amount_cents=amount, item_skus=skus, reason="r")
    )


def store_credit(amount: int = 2000, order_id: str | None = None) -> ActionIntent:
    return intent(
        IssueStoreCreditArgs(customer_id=ALICE, order_id=order_id, amount_cents=amount, reason="r")
    )


def cancel(order_id: str = ORDER) -> ActionIntent:
    return intent(CancelOrderArgs(order_id=order_id, reason="r"))


def update_address(country: str = "US", order_id: str = ORDER) -> ActionIntent:
    return intent(
        UpdateAddressArgs(order_id=order_id, new_address=address(country, line1="99 New Road"))
    )


def ticket(order_id: str | None = None) -> ActionIntent:
    return intent(CreateTicketArgs(order_id=order_id, subject="s", body="b"))


def escalate() -> ActionIntent:
    return intent(EscalateToHumanArgs(reason="customer asked for a human"))


def follow_up(order_id: str | None = ORDER, hours: int = 48) -> ActionIntent:
    return intent(
        ScheduleFollowUpArgs(due_at=NOW + timedelta(hours=hours), order_id=order_id, note="check")
    )


def run(
    the_intent: ActionIntent,
    *orders: Order,
    sess: SessionContext | None = None,
    credits: list[tuple[str, datetime, int]] | None = None,
    policy_version: str = "2026.11.21-1",
) -> Decision:
    policy = REGISTRY.get("larkspur-returns", policy_version)
    return decide(
        the_intent,
        policy,
        session=sess or session(),
        source=FakeSource.with_(*orders, credits=credits),
        clock=SimulatedClock(NOW),
    )


def rule_outcomes(decision: Decision) -> dict[str, str]:
    return {r.rule_id: r.outcome.value for r in decision.rule_results}
