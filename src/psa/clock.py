"""Time source abstraction. All time-dependent logic takes a Clock, never datetime.now()."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulatedClock:
    """Deterministic clock for evals and tests. Only moves when told to."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("SimulatedClock requires a timezone-aware start time")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> datetime:
        if delta < timedelta(0):
            raise ValueError("SimulatedClock cannot move backwards")
        self._now += delta
        return self._now

    def set(self, when: datetime) -> datetime:
        if when.tzinfo is None:
            raise ValueError("SimulatedClock requires timezone-aware times")
        when = when.astimezone(UTC)
        if when < self._now:
            raise ValueError("SimulatedClock cannot move backwards")
        self._now = when
        return self._now
