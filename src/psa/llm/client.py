"""The LLMClient protocol every adapter implements."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from psa.llm.types import ModelResponse, NativeMessage, ToolOutput, ToolSpec


class LLMError(RuntimeError):
    """A model call failed after the adapter's own retries."""


@runtime_checkable
class LLMClient(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    def complete(
        self,
        *,
        system: str,
        transcript: Sequence[NativeMessage],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResponse:
        """One model call. Raises LLMError on unrecoverable failure."""
        ...

    def user_message(self, text: str) -> NativeMessage:
        """Native message carrying a user's text."""
        ...

    def tool_results_message(self, outputs: Sequence[ToolOutput]) -> NativeMessage:
        """Native message returning ALL results of one assistant turn's tool calls."""
        ...
