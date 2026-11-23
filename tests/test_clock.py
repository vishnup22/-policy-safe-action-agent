from datetime import UTC, datetime, timedelta, timezone

import pytest

from psa.clock import Clock, SimulatedClock, SystemClock

START = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


def test_system_clock_is_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert isinstance(SystemClock(), Clock)


def test_simulated_clock_advances_and_sets() -> None:
    clock = SimulatedClock(START)
    assert clock.now() == START
    assert clock.advance(timedelta(days=2)) == START + timedelta(days=2)
    assert clock.set(START + timedelta(days=3)) == START + timedelta(days=3)


def test_simulated_clock_normalizes_to_utc() -> None:
    ist = timezone(timedelta(hours=5, minutes=30))
    clock = SimulatedClock(START.astimezone(ist))
    assert clock.now().tzinfo is UTC
    assert clock.now() == START


@pytest.mark.parametrize(
    "action",
    [
        lambda c: c.advance(timedelta(seconds=-1)),
        lambda c: c.set(START - timedelta(seconds=1)),
        lambda c: c.set(datetime(2026, 11, 22)),
    ],
)
def test_simulated_clock_rejects_invalid_moves(action) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        action(SimulatedClock(START))


def test_simulated_clock_requires_aware_start() -> None:
    with pytest.raises(ValueError):
        SimulatedClock(datetime(2026, 11, 21))
