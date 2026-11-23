"""Deterministic fault injection for eval scenarios (RuntimeConfig.faults)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from psa.runtime.ports import ToolFault
from psa.tools.errors import ToolFailure
from psa.tools.payments import PaymentsGateway, RefundReceipt

PAYMENTS_REFUND = "payments.refund"


class FaultInjector:
    """Counts calls per tool; the Nth call of a tool fails if a fault targets it."""

    def __init__(self, faults: Iterable[ToolFault] = ()) -> None:
        self._faults = {(f.tool, f.on_call): f for f in faults}
        self._calls: Counter[str] = Counter()

    def before_call(self, tool: str) -> None:
        self._calls[tool] += 1
        fault = self._faults.get((tool, self._calls[tool]))
        if fault is not None:
            raise ToolFailure.from_fault(fault.mode, tool)

    def calls(self, tool: str) -> int:
        return self._calls[tool]


@dataclass(frozen=True)
class FaultInjectingPayments:
    """Inject refund faults at the gateway boundary before forwarding the payment call."""

    gateway: PaymentsGateway
    faults: FaultInjector

    @property
    def name(self) -> str:
        return self.gateway.name

    def refund(
        self, *, payment_intent_id: str | None, amount_cents: int, idempotency_key: str
    ) -> RefundReceipt:
        self.faults.before_call(PAYMENTS_REFUND)
        return self.gateway.refund(
            payment_intent_id=payment_intent_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
        )
