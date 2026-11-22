"""Provider-neutral LLM types.

Transcripts are kept in each provider's NATIVE message format (a list of JSON dicts) and are
append-only: assistant turns are stored exactly as the provider returned them (including any
thinking blocks), because current models require those to be sent back unchanged. Only the
adapter that produced a transcript may read it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

NativeMessage = dict[str, Any]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolSpec(_Frozen):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    description: str
    input_schema: dict[str, Any]


class ToolCall(_Frozen):
    call_id: str
    name: str
    arguments: dict[str, Any]


class ToolOutput(_Frozen):
    call_id: str
    content: str = Field(description="JSON-encoded result or error text")
    is_error: bool = False


class Usage(_Frozen):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class ModelResponse(_Frozen):
    text: str = Field(description="Concatenated visible text blocks")
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: str
    refused: bool = False
    usage: Usage = Usage()
    model: str = Field(description="Model that actually served the request")
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    assistant_message: NativeMessage = Field(
        description="Native assistant turn to append to the transcript, unchanged"
    )
