"""Provider-neutral LLM client. Provider and model are configuration, never code."""

from __future__ import annotations

import os

from psa.llm.client import LLMClient, LLMError
from psa.llm.scripted import ScriptedLLM, Step
from psa.llm.types import ModelResponse, NativeMessage, ToolCall, ToolOutput, ToolSpec, Usage

OPENAI_COMPATIBLE_DEFAULT_URLS = {
    "ollama_openai": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "huggingface": "https://router.huggingface.co/v1",
    "openai_compat": "",
}


def client_from_env(prefix: str = "LLM") -> LLMClient:
    """Build a client from <PREFIX>_PROVIDER / _MODEL / _API_KEY and provider-specific vars.

    Providers: ollama (native API, sets the context window), lmstudio, openrouter, groq,
    huggingface, openai_compat (any OpenAI-compatible server; set <PREFIX>_BASE_URL), anthropic.
    """
    provider = os.environ.get(f"{prefix}_PROVIDER", "ollama").strip().lower()
    model = os.environ.get(f"{prefix}_MODEL", "").strip()
    temperature_raw = os.environ.get(f"{prefix}_TEMPERATURE", "0.2").strip()
    temperature = float(temperature_raw) if temperature_raw else None
    if provider == "ollama":
        from psa.llm.ollama_client import DEFAULT_URL, OllamaClient

        return OllamaClient(
            model=model,
            base_url=os.environ.get(f"{prefix}_BASE_URL", "").strip() or DEFAULT_URL,
            num_ctx=int(os.environ.get(f"{prefix}_NUM_CTX", "16384")),
            temperature=temperature,
            max_retries=int(os.environ.get(f"{prefix}_MAX_RETRIES", "3")),
            timeout_s=float(os.environ.get(f"{prefix}_TIMEOUT_S", "600")),
        )
    if provider in OPENAI_COMPATIBLE_DEFAULT_URLS:
        from psa.llm.openai_compat import OpenAICompatibleClient

        return OpenAICompatibleClient(
            model=model,
            base_url=os.environ.get(f"{prefix}_BASE_URL", "").strip()
            or OPENAI_COMPATIBLE_DEFAULT_URLS[provider],
            api_key=os.environ.get(f"{prefix}_API_KEY") or None,
            provider_name=provider,
            temperature=temperature,
            max_retries=int(os.environ.get(f"{prefix}_MAX_RETRIES", "3")),
            timeout_s=float(os.environ.get(f"{prefix}_TIMEOUT_S", "300")),
        )
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
