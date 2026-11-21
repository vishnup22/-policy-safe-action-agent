"""Fact registry and resolver.

Facts are the ONLY inputs to policy decisions. Each fact is computed from the system of
record (a FactSource) plus the structured intent arguments and the authenticated session.
Nothing here ever reads conversation text or `intent.justification`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from psa.clock import Clock
from psa.domain import (
    ActionIntent,
    ActionName,
    Customer,
    IssueRefundArgs,
    IssueStoreCreditArgs,
    ItemCategory,
    Order,
    OrderItem,
    OrderStatus,
    ScheduleFollowUpArgs,
    UpdateAddressArgs,
)

FactValue = int | str | bool
SECONDS_PER_DAY = 86_400
STORE_CREDIT_WINDOW = timedelta(days=30)

ORDER_ACTIONS: frozenset[ActionName] = frozenset(
    {
        ActionName.ISSUE_REFUND,
        ActionName.ISSUE_STORE_CREDIT,
        ActionName.CANCEL_ORDER,
        ActionName.UPDATE_ADDRESS,
        ActionName.CREATE_TICKET,
        ActionName.SCHEDULE_FOLLOW_UP,
    }
)
"""Actions whose args can reference an order (order_id may be optional for some)."""


class FactType(StrEnum):
    INT = "int"
    STR = "str"
    BOOL = "bool"


@dataclass(frozen=True)
class MissingFact:
    """A fact that could not be resolved. Policies treat this as fail-closed."""

    reason: str


@dataclass(frozen=True)
class SessionContext:
    """Server-side session state. `identity_verified` is set by the verification flow only."""

    conversation_id: str
    customer_id: str | None
    identity_verified: bool


class FactSource(Protocol):
    """Read-only access to the system of record."""

    def get_order(self, order_id: str) -> Order | None: ...

    def get_customer(self, customer_id: str) -> Customer | None: ...

    def store_credit_issued_cents(self, customer_id: str, since: datetime) -> int: ...


@dataclass
class FactContext:
    intent: ActionIntent
    session: SessionContext
    source: FactSource
    clock: Clock
    _orders: dict[str, Order | None] = field(default_factory=dict[str, "Order | None"])
    _customers: dict[str, Customer | None] = field(default_factory=dict[str, "Customer | None"])
    _now: datetime | None = None

    @property
    def now(self) -> datetime:
        # One consistent "now" per evaluation, even if the clock moves.
        if self._now is None:
            self._now = self.clock.now()
        return self._now

    def order_id(self) -> str | None:
        order_id: object = getattr(self.intent.args, "order_id", None)
        return order_id if isinstance(order_id, str) else None

    def order(self) -> Order | MissingFact:
        order_id = self.order_id()
        if order_id is None:
            return MissingFact("intent does not reference an order")
        if order_id not in self._orders:
            self._orders[order_id] = self.source.get_order(order_id)
        order = self._orders[order_id]
        return order if order is not None else MissingFact(f"order {order_id} not found")

    def session_customer(self) -> Customer | MissingFact:
        customer_id = self.session.customer_id
        if customer_id is None:
            return MissingFact("session has no customer")
        if customer_id not in self._customers:
            self._customers[customer_id] = self.source.get_customer(customer_id)
        customer = self._customers[customer_id]
        return customer if customer is not None else MissingFact("session customer not found")


Resolver = Callable[[FactContext], FactValue | MissingFact]


@dataclass(frozen=True)
class FactSpec:
    name: str
    type: FactType
    description: str
    resolve: Resolver
    actions: frozenset[ActionName] | None = None
    """Actions for which this fact is meaningful; None means all actions."""
    allowed_values: frozenset[str] | None = None
    """For STR facts with a closed vocabulary; policies are validated against it."""


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


def _targeted_items(ctx: FactContext) -> tuple[OrderItem, ...] | MissingFact:
    args = ctx.intent.args
    order = ctx.order()
    if isinstance(order, MissingFact):
        return order
    if not isinstance(args, IssueRefundArgs) or not args.item_skus:
        return order.items
    by_sku = {item.sku: item for item in order.items}
    if any(sku not in by_sku for sku in args.item_skus):
        return MissingFact("refund references SKUs not in the order")
    return tuple(by_sku[sku] for sku in args.item_skus)


def _intent_amount(ctx: FactContext) -> FactValue | MissingFact:
    args = ctx.intent.args
    if isinstance(args, IssueRefundArgs | IssueStoreCreditArgs):
        return args.amount_cents
    return MissingFact("action has no amount")


def _items_in_order(ctx: FactContext) -> FactValue | MissingFact:
    args = ctx.intent.args
    order = ctx.order()
    if isinstance(order, MissingFact):
        return order
    if not isinstance(args, IssueRefundArgs):
        return MissingFact("action has no item list")
    skus = {item.sku for item in order.items}
    return all(sku in skus for sku in args.item_skus)


def _includes_final_sale(ctx: FactContext) -> FactValue | MissingFact:
    items = _targeted_items(ctx)
    if isinstance(items, MissingFact):
        return items
    return any(item.final_sale for item in items)


def _includes_gift_card(ctx: FactContext) -> FactValue | MissingFact:
    items = _targeted_items(ctx)
    if isinstance(items, MissingFact):
        return items
    return any(item.category is ItemCategory.GIFT_CARD for item in items)


def _address_country_changed(ctx: FactContext) -> FactValue | MissingFact:
    args = ctx.intent.args
    order = ctx.order()
    if isinstance(order, MissingFact):
        return order
    if not isinstance(args, UpdateAddressArgs):
        return MissingFact("action has no new address")
    return args.new_address.country != order.shipping_address.country


def _follow_up_hours_ahead(ctx: FactContext) -> FactValue | MissingFact:
    args = ctx.intent.args
    if not isinstance(args, ScheduleFollowUpArgs):
        return MissingFact("action has no due time")
    return int((args.due_at - ctx.now).total_seconds() // 3600)


def _order_exists(ctx: FactContext) -> FactValue | MissingFact:
    if ctx.order_id() is None:
        return MissingFact("intent does not reference an order")
    return not isinstance(ctx.order(), MissingFact)


def _order_status(ctx: FactContext) -> FactValue | MissingFact:
    order = ctx.order()
    return order if isinstance(order, MissingFact) else order.status.value


def _order_owned(ctx: FactContext) -> FactValue | MissingFact:
    order = ctx.order()
    if isinstance(order, MissingFact):
        return order
    return ctx.session.customer_id is not None and order.customer_id == ctx.session.customer_id


def _days_since_delivery(ctx: FactContext) -> FactValue | MissingFact:
    order = ctx.order()
    if isinstance(order, MissingFact):
        return order
    if order.delivered_at is None:
        return MissingFact("order has not been delivered")
    elapsed = (ctx.now - order.delivered_at).total_seconds()
    if elapsed < 0:
        return MissingFact("delivery time is in the future (inconsistent record)")
    return int(elapsed // SECONDS_PER_DAY)


def _amount_refundable(ctx: FactContext) -> FactValue | MissingFact:
    order = ctx.order()
    return order if isinstance(order, MissingFact) else order.amount_refundable_cents


_SHIPPED_STATUSES = frozenset(
    {
        OrderStatus.SHIPPED,
        OrderStatus.DELIVERED,
        OrderStatus.PARTIALLY_REFUNDED,
        OrderStatus.REFUNDED,
    }
)


def _order_shipped(ctx: FactContext) -> FactValue | MissingFact:
    order = ctx.order()
    if isinstance(order, MissingFact):
        return order
    return order.shipped_at is not None or order.status in _SHIPPED_STATUSES


def _customer_tier(ctx: FactContext) -> FactValue | MissingFact:
    customer = ctx.session_customer()
    return customer if isinstance(customer, MissingFact) else customer.tier.value


def _store_credit_30d(ctx: FactContext) -> FactValue | MissingFact:
    customer = ctx.session_customer()
    if isinstance(customer, MissingFact):
        return customer
    return ctx.source.store_credit_issued_cents(customer.customer_id, ctx.now - STORE_CREDIT_WINDOW)


def _store_credit_after_intent(ctx: FactContext) -> FactValue | MissingFact:
    issued = _store_credit_30d(ctx)
    amount = _intent_amount(ctx)
    if isinstance(issued, MissingFact):
        return issued
    if isinstance(amount, MissingFact):
        return amount
    return int(issued) + int(amount)


def _has_order(ctx: FactContext) -> FactValue | MissingFact:
    return ctx.order_id() is not None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_MONEY = frozenset({ActionName.ISSUE_REFUND, ActionName.ISSUE_STORE_CREDIT})
_REFUND = frozenset({ActionName.ISSUE_REFUND})

_SPECS: tuple[FactSpec, ...] = (
    FactSpec(
        "session.identity_verified",
        FactType.BOOL,
        "Customer identity verified by the server-side verification flow",
        lambda ctx: ctx.session.identity_verified,
    ),
    FactSpec(
        "session.has_customer",
        FactType.BOOL,
        "Session is linked to a known customer",
        lambda ctx: ctx.session.customer_id is not None,
    ),
    FactSpec("intent.has_order", FactType.BOOL, "Intent references an order", _has_order),
    FactSpec(
        "intent.amount_cents", FactType.INT, "Requested amount in cents", _intent_amount, _MONEY
    ),
    FactSpec(
        "intent.items_in_order",
        FactType.BOOL,
        "Every SKU named in the refund belongs to the order",
        _items_in_order,
        _REFUND,
    ),
    FactSpec(
        "intent.includes_final_sale",
        FactType.BOOL,
        "Refund targets at least one final-sale item",
        _includes_final_sale,
        _REFUND,
    ),
    FactSpec(
        "intent.includes_gift_card",
        FactType.BOOL,
        "Refund targets at least one gift card",
        _includes_gift_card,
        _REFUND,
    ),
    FactSpec(
        "intent.address_country_changed",
        FactType.BOOL,
        "New shipping address is in a different country than the current one",
        _address_country_changed,
        frozenset({ActionName.UPDATE_ADDRESS}),
    ),
    FactSpec(
        "intent.follow_up_hours_ahead",
        FactType.INT,
        "Whole hours between now and the requested follow-up time",
        _follow_up_hours_ahead,
        frozenset({ActionName.SCHEDULE_FOLLOW_UP}),
    ),
    FactSpec(
        "order.exists", FactType.BOOL, "Referenced order exists", _order_exists, ORDER_ACTIONS
    ),
    FactSpec(
        "order.status",
        FactType.STR,
        "Current order status",
        _order_status,
        ORDER_ACTIONS,
        frozenset(s.value for s in OrderStatus),
    ),
    FactSpec(
        "order.owned_by_session_customer",
        FactType.BOOL,
        "Order belongs to the session's customer",
        _order_owned,
        ORDER_ACTIONS,
    ),
    FactSpec(
        "order.days_since_delivery",
        FactType.INT,
        "Whole days since delivery (missing if not delivered)",
        _days_since_delivery,
        ORDER_ACTIONS,
    ),
    FactSpec(
        "order.amount_refundable_cents",
        FactType.INT,
        "Amount paid minus amount already refunded",
        _amount_refundable,
        ORDER_ACTIONS,
    ),
    FactSpec(
        "order.is_shipped",
        FactType.BOOL,
        "Order has left the warehouse",
        _order_shipped,
        ORDER_ACTIONS,
    ),
    FactSpec(
        "customer.tier",
        FactType.STR,
        "Loyalty tier of the session customer",
        _customer_tier,
        None,
        frozenset({"standard", "plus", "vip"}),
    ),
    FactSpec(
        "customer.store_credit_30d_cents",
        FactType.INT,
        "Store credit issued to the session customer in the last 30 days",
        _store_credit_30d,
    ),
    FactSpec(
        "customer.store_credit_30d_after_intent_cents",
        FactType.INT,
        "Store credit in the last 30 days including this request",
        _store_credit_after_intent,
        frozenset({ActionName.ISSUE_STORE_CREDIT}),
    ),
)

FACTS: Mapping[str, FactSpec] = {spec.name: spec for spec in _SPECS}


@dataclass(frozen=True)
class ResolvedFacts:
    values: Mapping[str, FactValue]
    missing: Mapping[str, str]


def resolve_facts(names: Iterable[str], ctx: FactContext) -> ResolvedFacts:
    """Resolve the given facts. Unknown names are reported as missing (fail closed)."""
    values: dict[str, FactValue] = {}
    missing: dict[str, str] = {}
    for name in sorted(set(names)):
        spec = FACTS.get(name)
        if spec is None:
            missing[name] = "unknown fact"
            continue
        result = spec.resolve(ctx)
        if isinstance(result, MissingFact):
            missing[name] = result.reason
        else:
            values[name] = result
    return ResolvedFacts(values=values, missing=missing)
