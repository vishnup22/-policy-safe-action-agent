"""Provider-neutral LLM client. Provider and model are configuration, never code."""

from __future__ import annotations

import os

from psa.llm.client import LLMClient, LLMError
from psa.llm.scripted import ScriptedLLM, Step
from psa.llm.types import ModelResponse, NativeMessage, ToolCall, ToolOutput, ToolSpec, Usage


def client_from_env(prefix: str = "LLM") -> LLMClient:
    """Build a client from <PREFIX>_PROVIDER / _MODEL / _API_KEY / _EFFORT / _FALLBACKS."""
    provider = os.environ.get(f"{prefix}_PROVIDER", "anthropic").strip().lower()
    model = os.environ.get(f"{prefix}_MODEL", "").strip()
    if provider == "anthropic":
        from psa.llm.anthropic_client import AnthropicClient

        return AnthropicClient(
            model=model,
            api_key=os.environ.get(f"{prefix}_API_KEY") or None,
            effort=os.environ.get(f"{prefix}_EFFORT", "medium") or None,
            fallbacks=os.environ.get(f"{prefix}_FALLBACKS", "default"),
            max_retries=int(os.environ.get(f"{prefix}_MAX_RETRIES", "3")),
        )
    raise LLMError(
        f"unsupported {prefix}_PROVIDER '{provider}'. Implement psa.llm.client.LLMClient "
        "for it and register it here."
    )


__all__ = [
    "LLMClient",
    "LLMError",
    "ModelResponse",
    "NativeMessage",
    "ScriptedLLM",
    "Step",
    "ToolCall",
    "ToolOutput",
    "ToolSpec",
    "Usage",
    "client_from_env",
]
