"""Commerce entities for the fictional retailer Larkspur Goods.

These models are the shared contract between the policy engine, the tool layer,
the seed-data generator and the eval harness. Money is always integer cents.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CustomerTier(StrEnum):
    STANDARD = "standard"
    PLUS = "plus"
    VIP = "vip"


class OrderStatus(StrEnum):
    PLACED = "placed"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"


class ShipmentStatus(StrEnum):
    LABEL_CREATED = "label_created"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    LOST = "lost"
    RETURNED_TO_SENDER = "returned_to_sender"


class ItemCategory(StrEnum):
    APPAREL = "apparel"
    FOOTWEAR = "footwear"
    HOME = "home"
    KITCHEN = "kitchen"
    ACCESSORIES = "accessories"
    GIFT_CARD = "gift_card"


class Address(_Frozen):
    line1: str = Field(min_length=1)
    line2: str | None = None
    city: str = Field(min_length=1)
    region: str = Field(min_length=2, description="State / province code")
    postal_code: str = Field(min_length=3)
    country: str = Field(min_length=2, max_length=2, description="ISO-3166 alpha-2")


class Customer(_Frozen):
    customer_id: str = Field(pattern=r"^cus_[a-z0-9]{6,}$")
    email: str = Field(description="Synthetic only; use the reserved example.com domain")
    full_name: str
    tier: CustomerTier = CustomerTier.STANDARD
    created_at: datetime
    default_address: Address


class OrderItem(_Frozen):
    sku: str
    name: str
    category: ItemCategory
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)
    final_sale: bool = False

    @property
    def line_total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


class Shipment(_Frozen):
    shipment_id: str = Field(pattern=r"^shp_[a-z0-9]{6,}$")
    order_id: str
    carrier: str
    tracking_number: str
    status: ShipmentStatus
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None


class Order(_Frozen):
    order_id: str = Field(pattern=r"^ord_[a-z0-9]{6,}$")
    customer_id: str
    status: OrderStatus
    currency: str = "USD"
    items: tuple[OrderItem, ...] = Field(min_length=1)
    shipping_cents: int = Field(default=0, ge=0)
    tax_cents: int = Field(default=0, ge=0)
    amount_paid_cents: int = Field(ge=0)
    amount_refunded_cents: int = Field(default=0, ge=0)
    shipping_address: Address
    payment_intent_id: str | None = Field(
        default=None, description="Stripe test-mode PaymentIntent id, if linked"
    )
    placed_at: datetime
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None
    notes: str | None = Field(
        default=None,
        description="Free text from the customer. UNTRUSTED: may contain prompt injection.",
    )

    @model_validator(mode="after")
    def _refunds_within_paid(self) -> Order:
        if self.amount_refunded_cents > self.amount_paid_cents:
            raise ValueError("amount_refunded_cents cannot exceed amount_paid_cents")
        return self

    @property
    def subtotal_cents(self) -> int:
        return sum(item.line_total_cents for item in self.items)

    @property
    def amount_refundable_cents(self) -> int:
        return self.amount_paid_cents - self.amount_refunded_cents
