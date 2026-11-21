"""SQLAlchemy models for the system of record and the append-only event log.

Conventions: money is BIGINT cents, all timestamps are timestamptz, structured values
(addresses, payloads) are JSONB. Enum columns are stored as strings with CHECK constraints.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from psa.domain import CustomerTier, EventType, ItemCategory, OrderStatus, ShipmentStatus
from psa.store.db import Base

TS = DateTime(timezone=True)


def _enum[E: StrEnum](enum: type[E], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FollowUpStatus(StrEnum):
    SCHEDULED = "scheduled"
    FIRED = "fired"
    CANCELLED = "cancelled"


class IdempotencyStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    AWAITING_APPROVAL = "awaiting_approval"
    ENDED = "ended"


# --------------------------------------------------------------------------- commerce


class CustomerRow(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[CustomerTier] = mapped_column(_enum(CustomerTier, "customer_tier"))
    created_at: Mapped[datetime] = mapped_column(TS)
    default_address: Mapped[dict[str, Any]] = mapped_column(JSONB)


class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_paid_cents >= 0", name="paid_non_negative"),
        CheckConstraint(
            "amount_refunded_cents >= 0 AND amount_refunded_cents <= amount_paid_cents",
            name="refund_within_paid",
        ),
        Index("ix_orders_customer_id", "customer_id"),
    )

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus, "order_status"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    shipping_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    tax_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    amount_paid_cents: Mapped[int] = mapped_column(BigInteger)
    amount_refunded_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    shipping_address: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payment_intent_id: Mapped[str | None] = mapped_column(String(128))
    placed_at: Mapped[datetime] = mapped_column(TS)
    shipped_at: Mapped[datetime | None] = mapped_column(TS)
    delivered_at: Mapped[datetime | None] = mapped_column(TS)
    notes: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[OrderItemRow]] = relationship(
        order_by="OrderItemRow.position", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItemRow(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "position", name="uq_order_items_order_position"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    position: Mapped[int] = mapped_column(Integer)
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[ItemCategory] = mapped_column(_enum(ItemCategory, "item_category"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)
    final_sale: Mapped[bool] = mapped_column(Boolean, default=False)


class ShipmentRow(Base):
    __tablename__ = "shipments"
    __table_args__ = (Index("ix_shipments_order_id", "order_id"),)

    shipment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    carrier: Mapped[str] = mapped_column(String(64))
    tracking_number: Mapped[str] = mapped_column(String(128))
    status: Mapped[ShipmentStatus] = mapped_column(_enum(ShipmentStatus, "shipment_status"))
    shipped_at: Mapped[datetime | None] = mapped_column(TS)
    delivered_at: Mapped[datetime | None] = mapped_column(TS)


class RefundRow(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        Index("ix_refunds_order_id", "order_id"),
    )

    refund_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    item_skus: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reason: Mapped[str] = mapped_column(Text)
    stripe_refund_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    intent_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(TS)


class StoreCreditRow(Base):
    __tablename__ = "store_credits"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        Index("ix_store_credits_customer_issued", "customer_id", "issued_at"),
    )

    credit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.order_id"))
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    intent_id: Mapped[str] = mapped_column(String(64))
    issued_at: Mapped[datetime] = mapped_column(TS)


# --------------------------------------------------------------------------- execution


class IdempotencyKeyRow(Base):
    """One row per side-effecting intent. The executor claims the key before acting."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    status: Mapped[IdempotencyStatus] = mapped_column(
        _enum(IdempotencyStatus, "idempotency_status")
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TS)
    updated_at: Mapped[datetime] = mapped_column(TS)


class ConversationRow(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.customer_id"))
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ConversationStatus] = mapped_column(
        _enum(ConversationStatus, "conversation_status")
    )
    started_at: Mapped[datetime] = mapped_column(TS)
    next_seq: Mapped[int] = mapped_column(Integer, default=0)


class EventRow(Base):
    """Append-only. A database trigger rejects UPDATE, DELETE and TRUNCATE."""

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_events_conversation_seq"),
        CheckConstraint("seq >= 0", name="seq_non_negative"),
        CheckConstraint(
            "type NOT IN ('policy_decision', 'action_executed') OR policy_version IS NOT NULL",
            name="policy_version_required",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.conversation_id"))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[EventType] = mapped_column(_enum(EventType, "event_type"))
    at: Mapped[datetime] = mapped_column(TS)
    policy_version: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_status_requested", "status", "requested_at"),)

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.conversation_id"))
    intent_id: Mapped[str] = mapped_column(String(64), unique=True)
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB)
    decision: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[ApprovalStatus] = mapped_column(_enum(ApprovalStatus, "approval_status"))
    requested_at: Mapped[datetime] = mapped_column(TS)
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    reviewer: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)


class FollowUpRow(Base):
    __tablename__ = "follow_ups"
    __table_args__ = (Index("ix_follow_ups_status_due", "status", "due_at"),)

    follow_up_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.conversation_id"))
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.order_id"))
    due_at: Mapped[datetime] = mapped_column(TS)
    note: Mapped[str] = mapped_column(Text)
    status: Mapped[FollowUpStatus] = mapped_column(_enum(FollowUpStatus, "follow_up_status"))
    fired_at: Mapped[datetime | None] = mapped_column(TS)
