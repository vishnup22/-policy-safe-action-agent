from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from psa.clock import SimulatedClock
from psa.executor import CircuitBreaker
from psa.runtime.ports import FaultMode, ToolFault
from psa.tools import (
    FaultInjector,
    LiveKeyError,
    SimulatedStripe,
    ToolFailure,
    ensure_test_key,
    gateway_from_env,
)


@pytest.mark.parametrize("key", ["sk_live_abc123", "rk_live_abc123"])
def test_live_keys_are_refused(key: str) -> None:
    with pytest.raises(LiveKeyError, match="LIVE"):
        ensure_test_key(key)


def test_non_stripe_key_refused() -> None:
    with pytest.raises(LiveKeyError, match="test-mode"):
        ensure_test_key("pk_test_publishable")


def test_live_key_in_env_aborts_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_realmoney")
    with pytest.raises(LiveKeyError):
        gateway_from_env()


@pytest.mark.parametrize("value", ["", "sk_test_replace_me", "sk_test_ci_placeholder"])
def test_placeholder_keys_use_simulator(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("STRIPE_SECRET_KEY", value)
    assert gateway_from_env().name == "stripe-sim"


def test_simulated_stripe_is_idempotent() -> None:
    gateway = SimulatedStripe()
    first = gateway.refund(payment_intent_id=None, amount_cents=100, idempotency_key="k1")
    again = gateway.refund(payment_intent_id=None, amount_cents=100, idempotency_key="k1")
    other = gateway.refund(payment_intent_id=None, amount_cents=100, idempotency_key="k2")
    assert first == again
    assert other.refund_id != first.refund_id
    assert gateway.calls == 2


def test_fault_injector_fails_exactly_the_nth_call() -> None:
    faults = FaultInjector([ToolFault(tool="issue_refund", mode=FaultMode.TIMEOUT, on_call=2)])
    faults.before_call("issue_refund")
    with pytest.raises(ToolFailure) as info:
        faults.before_call("issue_refund")
    assert info.value.retryable
    faults.before_call("issue_refund")
    faults.before_call("get_order")
    assert faults.calls("issue_refund") == 3


@pytest.mark.parametrize(
    ("mode", "retryable"),
    [
        (FaultMode.TIMEOUT, True),
        (FaultMode.ERROR_5XX, True),
        (FaultMode.RATE_LIMITED, True),
        (FaultMode.CARD_DECLINED, False),
    ],
)
def test_fault_retryability(mode: FaultMode, retryable: bool) -> None:
    assert ToolFailure.from_fault(mode, "t").retryable is retryable


def test_circuit_breaker_opens_and_half_opens() -> None:
    clock = SimulatedClock(datetime(2026, 11, 21, tzinfo=UTC))
    breaker = CircuitBreaker(clock, threshold=2, cooldown=timedelta(seconds=30))
    assert breaker.allow("t")
    breaker.record("t", ok=False)
    breaker.record("t", ok=False)
    assert not breaker.allow("t")
    clock.advance(timedelta(seconds=31))
    assert breaker.allow("t")  # half-open trial
    breaker.record("t", ok=False)
    assert not breaker.allow("t")  # one more failure re-opens immediately
    clock.advance(timedelta(seconds=31))
    breaker.allow("t")
    breaker.record("t", ok=True)
    assert breaker.allow("t")
