"""Payment gateways. Stripe TEST MODE only; a live key aborts startup.

Both gateways are idempotent on `idempotency_key`: repeating a refund with the same key returns
the original refund instead of moving money twice (Stripe enforces this server-side).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from typing import Protocol

from psa.tools.errors import LiveKeyError, ToolFailure


def ensure_test_key(key: str) -> str:
    if key.startswith(("sk_live_", "rk_live_")):
        raise LiveKeyError(
            "A LIVE Stripe key is configured. This project only runs in Stripe test mode; "
            "use an sk_test_ key."
        )
    if not key.startswith(("sk_test_", "rk_test_")):
        raise LiveKeyError("STRIPE_SECRET_KEY must be a Stripe test-mode key (sk_test_...)")
    return key


@dataclass(frozen=True)
class RefundReceipt:
    refund_id: str
    amount_cents: int
    gateway: str


class PaymentsGateway(Protocol):
    @property
    def name(self) -> str: ...

    def refund(
        self, *, payment_intent_id: str | None, amount_cents: int, idempotency_key: str
    ) -> RefundReceipt: ...


@dataclass
class SimulatedStripe:
    """In-process stand-in used when no Stripe key is set (and in tests)."""

    receipts: dict[str, RefundReceipt] = field(default_factory=dict[str, RefundReceipt])
    calls: int = 0

    @property
    def name(self) -> str:
        return "stripe-sim"

    def refund(
        self, *, payment_intent_id: str | None, amount_cents: int, idempotency_key: str
    ) -> RefundReceipt:
        existing = self.receipts.get(idempotency_key)
        if existing is not None:
            return existing
        self.calls += 1
        receipt = RefundReceipt(f"re_sim_{secrets.token_hex(8)}", amount_cents, self.name)
        self.receipts[idempotency_key] = receipt
        return receipt


class StripeTestGateway:
    """Real Stripe API in test mode.

    Synthetic orders have no real charge, so when an order lacks a PaymentIntent we create and
    confirm a test-mode one with Stripe's test card token before refunding it. Both calls carry
    idempotency keys derived from the intent's key.
    """

    def __init__(self, api_key: str) -> None:
        import stripe

        self._stripe = stripe
        self._client = stripe.StripeClient(ensure_test_key(api_key))

    @property
    def name(self) -> str:
        return "stripe-test"

    def refund(
        self, *, payment_intent_id: str | None, amount_cents: int, idempotency_key: str
    ) -> RefundReceipt:
        stripe = self._stripe
        try:
            if payment_intent_id is None:
                intent = self._client.v1.payment_intents.create(
                    {
                        "amount": amount_cents,
                        "currency": "usd",
                        "payment_method": "pm_card_visa",
                        "confirm": True,
                        "automatic_payment_methods": {
                            "enabled": True,
                            "allow_redirects": "never",
                        },
                    },
                    {"idempotency_key": f"{idempotency_key}-pi"},
                )
                payment_intent_id = intent.id
            refund = self._client.v1.refunds.create(
                {"payment_intent": payment_intent_id, "amount": amount_cents},
                {"idempotency_key": idempotency_key},
            )
        except stripe.CardError as exc:
            raise ToolFailure("card_declined", str(exc.user_message or exc)) from exc
        except stripe.RateLimitError as exc:
            raise ToolFailure("rate_limited", "Stripe rate limit", retryable=True) from exc
        except stripe.APIConnectionError as exc:
            raise ToolFailure("timeout", "could not reach Stripe", retryable=True) from exc
        except stripe.StripeError as exc:
            retryable = bool(exc.http_status and exc.http_status >= 500)
            raise ToolFailure("payment_error", str(exc), retryable=retryable) from exc
        return RefundReceipt(refund.id, amount_cents, self.name)


def gateway_from_env() -> PaymentsGateway:
    """Stripe test mode if STRIPE_SECRET_KEY is a real test key, else the simulator."""
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if not key or key in {"sk_test_replace_me", "sk_test_ci_placeholder"}:
        return SimulatedStripe()
    return StripeTestGateway(key)
