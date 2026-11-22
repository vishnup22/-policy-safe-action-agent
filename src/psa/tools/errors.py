"""Tool failure types. `retryable` drives the executor's retry policy."""

from __future__ import annotations

from psa.runtime.ports import FaultMode

RETRYABLE_MODES: frozenset[FaultMode] = frozenset(
    {FaultMode.TIMEOUT, FaultMode.ERROR_5XX, FaultMode.RATE_LIMITED}
)


class ToolFailure(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable

    @classmethod
    def from_fault(cls, mode: FaultMode, tool: str) -> ToolFailure:
        messages = {
            FaultMode.TIMEOUT: f"{tool} timed out",
            FaultMode.ERROR_5XX: f"{tool} upstream returned 503",
            FaultMode.RATE_LIMITED: f"{tool} was rate limited (429)",
            FaultMode.CARD_DECLINED: "the card issuer declined the refund",
        }
        return cls(mode.value, messages[mode], retryable=mode in RETRYABLE_MODES)


class NotFoundError(ToolFailure):
    def __init__(self, what: str) -> None:
        super().__init__("not_found", f"{what} not found")


class InvalidInputError(ToolFailure):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_input", message)


class LiveKeyError(RuntimeError):
    """Raised at startup if a live Stripe key is configured. This POC is test-mode only."""
