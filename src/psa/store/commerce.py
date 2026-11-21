"""System-of-record repository. Implements `psa.policy.FactSource` for the policy engine."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from psa.domain import Address, Customer, Order, OrderItem, Shipment
from psa.store.models import CustomerRow, OrderItemRow, OrderRow, ShipmentRow, StoreCreditRow


def _customer(row: CustomerRow) -> Customer:
    return Customer(
        customer_id=row.customer_id,
        email=row.email,
        full_name=row.full_name,
        tier=row.tier,
        created_at=row.created_at,
        default_address=Address.model_validate(row.default_address),
    )


def _order(row: OrderRow) -> Order:
    return Order(
        order_id=row.order_id,
        customer_id=row.customer_id,
        status=row.status,
        currency=row.currency,
        items=tuple(
            OrderItem(
                sku=i.sku,
                name=i.name,
                category=i.category,
                quantity=i.quantity,
                unit_price_cents=i.unit_price_cents,
                final_sale=i.final_sale,
            )
            for i in row.items
        ),
        shipping_cents=row.shipping_cents,
        tax_cents=row.tax_cents,
        amount_paid_cents=row.amount_paid_cents,
        amount_refunded_cents=row.amount_refunded_cents,
        shipping_address=Address.model_validate(row.shipping_address),
        payment_intent_id=row.payment_intent_id,
        placed_at=row.placed_at,
        shipped_at=row.shipped_at,
        delivered_at=row.delivered_at,
        notes=row.notes,
    )


class CommerceRepo:
    """Read/write access to commerce data. Read methods satisfy the FactSource protocol."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ FactSource

    def get_order(self, order_id: str) -> Order | None:
        row = self._session.get(OrderRow, order_id)
        return _order(row) if row is not None else None

    def get_customer(self, customer_id: str) -> Customer | None:
        row = self._session.get(CustomerRow, customer_id)
        return _customer(row) if row is not None else None

    def store_credit_issued_cents(self, customer_id: str, since: datetime) -> int:
        total = self._session.scalar(
            select(func.coalesce(func.sum(StoreCreditRow.amount_cents), 0)).where(
                StoreCreditRow.customer_id == customer_id,
                StoreCreditRow.issued_at >= since,
            )
        )
        return int(total or 0)

    # ------------------------------------------------------------------ reads

    def orders_for_customer(self, customer_id: str) -> list[Order]:
        rows = self._session.scalars(
            select(OrderRow).where(OrderRow.customer_id == customer_id).order_by(OrderRow.placed_at)
        )
        return [_order(row) for row in rows]

    def find_customer_by_email(self, email: str) -> Customer | None:
        row = self._session.scalar(select(CustomerRow).where(CustomerRow.email == email))
        return _customer(row) if row is not None else None

    def shipments_for_order(self, order_id: str) -> list[Shipment]:
        rows = self._session.scalars(select(ShipmentRow).where(ShipmentRow.order_id == order_id))
        return [
            Shipment(
                shipment_id=r.shipment_id,
                order_id=r.order_id,
                carrier=r.carrier,
                tracking_number=r.tracking_number,
                status=r.status,
                shipped_at=r.shipped_at,
                delivered_at=r.delivered_at,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ writes (seeding)

    def add_customer(self, customer: Customer) -> None:
        self._session.add(
            CustomerRow(
                customer_id=customer.customer_id,
                email=customer.email,
                full_name=customer.full_name,
                tier=customer.tier,
                created_at=customer.created_at,
                default_address=customer.default_address.model_dump(mode="json"),
            )
        )
        self._session.flush()

    def add_order(self, order: Order) -> None:
        row = OrderRow(
            order_id=order.order_id,
            customer_id=order.customer_id,
            status=order.status,
            currency=order.currency,
            shipping_cents=order.shipping_cents,
            tax_cents=order.tax_cents,
            amount_paid_cents=order.amount_paid_cents,
            amount_refunded_cents=order.amount_refunded_cents,
            shipping_address=order.shipping_address.model_dump(mode="json"),
            payment_intent_id=order.payment_intent_id,
            placed_at=order.placed_at,
            shipped_at=order.shipped_at,
            delivered_at=order.delivered_at,
            notes=order.notes,
            items=[
                OrderItemRow(
                    position=pos,
                    sku=i.sku,
                    name=i.name,
                    category=i.category,
                    quantity=i.quantity,
                    unit_price_cents=i.unit_price_cents,
                    final_sale=i.final_sale,
                )
                for pos, i in enumerate(order.items)
            ],
        )
        self._session.add(row)
        self._session.flush()

    def add_shipment(self, shipment: Shipment) -> None:
        self._session.add(
            ShipmentRow(
                shipment_id=shipment.shipment_id,
                order_id=shipment.order_id,
                carrier=shipment.carrier,
                tracking_number=shipment.tracking_number,
                status=shipment.status,
                shipped_at=shipment.shipped_at,
                delivered_at=shipment.delivered_at,
            )
        )
        self._session.flush()

    def add_store_credit(
        self,
        *,
        credit_id: str,
        customer_id: str,
        amount_cents: int,
        issued_at: datetime,
        idempotency_key: str,
        intent_id: str,
        reason: str,
        order_id: str | None = None,
    ) -> None:
        self._session.add(
            StoreCreditRow(
                credit_id=credit_id,
                customer_id=customer_id,
                order_id=order_id,
                amount_cents=amount_cents,
                reason=reason,
                idempotency_key=idempotency_key,
                intent_id=intent_id,
                issued_at=issued_at,
            )
        )
        self._session.flush()
