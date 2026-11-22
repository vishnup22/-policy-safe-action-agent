"""Adapter for any OpenAI-compatible Chat Completions endpoint.

One adapter covers free / open-weight setups:
  - Ollama (local):        LLM_BASE_URL=http://localhost:11434/v1
  - LM Studio (local):     LLM_BASE_URL=http://localhost:1234/v1
  - vLLM / llama.cpp:      LLM_BASE_URL=http://<host>:8000/v1
  - OpenRouter, Groq, Hugging Face router, Together...: their /v1 base URL + LLM_API_KEY

Uses plain httpx (no vendor SDK). The model must support native tool calling.

Native transcript format is the Chat Completions message list. The results of one assistant
turn's tool calls are stored as a single {"role": "_tool_batch", "messages": [...]} entry so
the LLMClient contract ("one message per tool-result batch") holds; it is flattened into
individual {"role": "tool"} messages when sent.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from typing import Any

import httpx

from psa.llm.client import LLMError
from psa.llm.pricing import cost_usd
from psa.llm.types import ModelResponse, NativeMessage, ToolCall, ToolOutput, ToolSpec, Usage

TOOL_BATCH = "_tool_batch"
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str | None = None,
        provider_name: str = "openai_compat",
        temperature: float | None = 0.2,
        max_tokens: int = 4096,
        max_retries: int = 3,
        timeout_s: float = 300.0,
        retry_backoff_s: float = 2.0,
        http: httpx.Client | None = None,
    ) -> None:
        if not model:
            raise ValueError("LLM model id is required (set LLM_MODEL)")
        if not base_url:
            raise ValueError("LLM_BASE_URL is required for OpenAI-compatible providers")
        self._model = model
        self._provider = provider_name
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._backoff = retry_backoff_s
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._http = http or httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s
        )

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    def user_message(self, text: str) -> NativeMessage:
        return {"role": "user", "content": text}

    def tool_results_message(self, outputs: Sequence[ToolOutput]) -> NativeMessage:
        return {
            "role": TOOL_BATCH,
            "messages": [
                {
                    "role": "tool",
                    "tool_call_id": o.call_id,
                    "content": f"ERROR: {o.content}" if o.is_error else o.content,
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
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *_flatten(transcript)],
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
            body["tool_choice"] = "auto"

        started = time.perf_counter()
        data = self._post(body)
        latency_ms = (time.perf_counter() - started) * 1000
        return _to_model_response(data, self._model, latency_ms)

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        last_error = "unknown error"
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.post("/chat/completions", json=body)
            except httpx.TimeoutException:
                last_error = "request timed out"
            except httpx.TransportError as exc:
                last_error = f"could not reach the model server ({exc.__class__.__name__})"
            else:
                if response.status_code == 200:
                    return response.json()
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code not in RETRYABLE_STATUS:
                    raise LLMError(f"{self._provider} rejected the request: {last_error}")
            if attempt < self._max_retries:
                time.sleep(self._backoff * (2**attempt))
        raise LLMError(f"{self._provider} failed after retries: {last_error}")


def _flatten(transcript: Sequence[NativeMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in transcript:
        if message.get("role") == TOOL_BATCH:
            out.extend(message["messages"])
        else:
            out.append(message)
    return out


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw  # some servers (e.g. older Ollama builds) send an object
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        # Surface as invalid input to the tool layer instead of crashing the turn.
        return {"_unparseable_arguments": str(raw)[:500]}
    return parsed if isinstance(parsed, dict) else {"_unparseable_arguments": str(raw)[:500]}


def _to_model_response(
    data: dict[str, Any], requested_model: str, latency_ms: float
) -> ModelResponse:
    choices = data.get("choices") or []
    if not choices:
        raise LLMError(f"model server returned no choices: {str(data)[:300]}")
    choice = choices[0]
    message: dict[str, Any] = dict(choice.get("message") or {})
    raw_calls: list[dict[str, Any]] = list(message.get("tool_calls") or [])
    calls: list[ToolCall] = []
    normalized_calls: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_calls):
        fn = raw.get("function") or {}
        call_id = str(raw.get("id") or f"call_{i}_{int(time.time() * 1000)}")
        arguments = _parse_arguments(fn.get("arguments"))
        calls.append(ToolCall(call_id=call_id, name=str(fn.get("name", "")), arguments=arguments))
        normalized_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {"name": fn.get("name", ""), "arguments": json.dumps(arguments)},
            }
        )
    text = str(message.get("content") or "").strip()
    assistant: dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
    if normalized_calls:
        assistant["tool_calls"] = normalized_calls
    raw_usage = data.get("usage") or {}
    usage = Usage(
        input_tokens=int(raw_usage.get("prompt_tokens") or 0),
        output_tokens=int(raw_usage.get("completion_tokens") or 0),
    )
    served_by = str(data.get("model") or requested_model)
    finish = str(choice.get("finish_reason") or ("tool_calls" if calls else "stop"))
    return ModelResponse(
        text=text,
        tool_calls=tuple(calls),
        stop_reason=finish,
        refused=finish == "content_filter",
        usage=usage,
        model=served_by,
        latency_ms=latency_ms,
        cost_usd=cost_usd(served_by, usage),  # 0 for local/open models unless priced via env
        assistant_message=assistant,
    )
