"""Anthropic Messages API adapter (official `anthropic` SDK).

- Manual tool loop: the agent owns orchestration (policy gate, event log), so we call
  `messages.create` directly and return the assistant content unchanged for the transcript.
- Thinking is left at the model default (adaptive on current models); depth is set with
  `output_config.effort` (LLM_EFFORT, default "medium") because defaults differ per model.
- `tool_choice` stays "auto": forcing a tool returns 400 on current models.
- Server-side refusal fallbacks are on by default (LLM_FALLBACKS="default"; set "off" to
  disable, e.g. for models that don't support it).
- The SDK retries 408/409/429/5xx and connection errors (LLM_MAX_RETRIES, default 3).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

import anthropic

from psa.llm.client import LLMError
from psa.llm.pricing import cost_usd
from psa.llm.types import ModelResponse, NativeMessage, ToolCall, ToolOutput, ToolSpec, Usage

FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_MAX_TOKENS = 16_000


class AnthropicClient:
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        effort: str | None = "medium",
        fallbacks: str = "default",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_retries: int = 3,
        timeout_s: float = 120.0,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        if not model:
            raise ValueError("LLM model id is required (set LLM_MODEL)")
        if fallbacks not in {"default", "off"}:
            raise ValueError("LLM_FALLBACKS must be 'default' or 'off'")
        self._model = model
        self._effort = effort
        self._fallbacks = fallbacks
        self._max_tokens = max_tokens
        # api_key=None lets the SDK resolve credentials (env var or `ant auth login` profile).
        self._client = client or anthropic.Anthropic(
            api_key=api_key or None, max_retries=max_retries, timeout=timeout_s
        )

    @property
    def provider(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def user_message(self, text: str) -> NativeMessage:
        return {"role": "user", "content": [{"type": "text", "text": text}]}

    def tool_results_message(self, outputs: Sequence[ToolOutput]) -> NativeMessage:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": o.call_id,
                    "content": o.content,
                    "is_error": o.is_error,
                }
                for o in outputs
            ],
        }

    def complete(
        self,
        *,
        system: str,
        transcript: Sequence[NativeMessage],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResponse:
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": list(transcript),
        }
        if tools:
            params["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
        if self._effort:
            params["output_config"] = {"effort": self._effort}

        started = time.perf_counter()
        try:
            if self._fallbacks == "default":
                response: Any = self._client.beta.messages.create(
                    **params, betas=[FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = self._client.messages.create(**params)
        except anthropic.BadRequestError as exc:
            raise LLMError(f"bad request to {self._model}: {exc.message}") from exc
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic authentication failed (check LLM_API_KEY)") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("rate limited after retries") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("could not reach the Anthropic API") from exc
        latency_ms = (time.perf_counter() - started) * 1000

        return _to_model_response(response, latency_ms)


def _to_model_response(response: Any, latency_ms: float) -> ModelResponse:
    blocks: list[dict[str, Any]] = [block.to_dict() for block in response.content]
    texts = [b["text"] for b in blocks if b.get("type") == "text"]
    calls = tuple(
        ToolCall(call_id=b["id"], name=b["name"], arguments=dict(b.get("input") or {}))
        for b in blocks
        if b.get("type") == "tool_use"
    )
    raw_usage = response.usage
    usage = Usage(
        input_tokens=raw_usage.input_tokens or 0,
        output_tokens=raw_usage.output_tokens or 0,
        cache_read_input_tokens=getattr(raw_usage, "cache_read_input_tokens", None) or 0,
        cache_creation_input_tokens=getattr(raw_usage, "cache_creation_input_tokens", None) or 0,
    )
    served_by = str(response.model)
    return ModelResponse(
        text="".join(texts).strip(),
        tool_calls=calls,
        stop_reason=str(response.stop_reason),
        refused=response.stop_reason == "refusal",
        usage=usage,
        model=served_by,
        latency_ms=latency_ms,
        cost_usd=cost_usd(served_by, usage),
        assistant_message={"role": "assistant", "content": blocks},
    )
