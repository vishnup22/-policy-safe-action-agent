"""Deterministic fault injection for eval scenarios (RuntimeConfig.faults)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from psa.runtime.ports import ToolFault
from psa.tools.errors import ToolFailure


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
