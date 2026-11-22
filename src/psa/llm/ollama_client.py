"""Native Ollama adapter (/api/chat).

Ollama's OpenAI-compatible endpoint can't set the context window, and its default is small
enough that the agent's tool definitions get silently truncated. The native API takes
`options.num_ctx`, so this adapter is the default for LLM_PROVIDER=ollama.
"""

from __future__ import annotations

import json
import secrets
import time
from collections.abc import Sequence
from typing import Any

import httpx

from psa.llm.client import LLMError
from psa.llm.openai_compat import RETRYABLE_STATUS, TOOL_BATCH
from psa.llm.types import ModelResponse, NativeMessage, ToolCall, ToolOutput, ToolSpec, Usage

DEFAULT_URL = "http://localhost:11434"


class OllamaClient:
    def __init__(
        self,
        *,
        model: str,
        base_url: str = DEFAULT_URL,
        num_ctx: int = 16_384,
        temperature: float | None = 0.2,
        max_retries: int = 3,
        timeout_s: float = 600.0,
        keep_alive: str = "30m",
        retry_backoff_s: float = 2.0,
        http: httpx.Client | None = None,
    ) -> None:
        if not model:
            raise ValueError("LLM model id is required (set LLM_MODEL, e.g. qwen2.5:14b)")
        self._model = model
        self._num_ctx = num_ctx
        self._temperature = temperature
        self._max_retries = max_retries
        self._keep_alive = keep_alive
        self._backoff = retry_backoff_s
        root = base_url.rstrip("/").removesuffix("/v1")
        self._http = http or httpx.Client(base_url=root, timeout=timeout_s)

    @property
    def provider(self) -> str:
        return "ollama"

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
        options: dict[str, Any] = {"num_ctx": self._num_ctx}
        if self._temperature is not None:
            options["temperature"] = self._temperature
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *self._flatten(transcript)],
            "stream": False,
            "options": options,
            "keep_alive": self._keep_alive,
        }
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
        started = time.perf_counter()
        data = self._post(body)
        latency_ms = (time.perf_counter() - started) * 1000
        return self._to_response(data, latency_ms)

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _flatten(transcript: Sequence[NativeMessage]) -> list[dict[str, Any]]:
        names: dict[str, str] = {}
        out: list[dict[str, Any]] = []
        for message in transcript:
            if message.get("role") == "assistant":
                for call in message.get("tool_calls") or []:
                    names[str(call.get("id"))] = str(call["function"]["name"])
                out.append(message)
            elif message.get("role") == TOOL_BATCH:
                for result in message["messages"]:
                    out.append(
                        {
                            "role": "tool",
                            "content": result["content"],
                            "tool_name": names.get(result["tool_call_id"], ""),
                        }
                    )
            else:
                out.append(message)
        return out

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        last_error = "unknown error"
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.post("/api/chat", json=body)
            except httpx.TimeoutException:
                last_error = "request timed out (is the model too large for this machine?)"
            except httpx.TransportError as exc:
                last_error = f"could not reach Ollama ({exc.__class__.__name__}); is it running?"
            else:
                if response.status_code == 200:
                    return response.json()
                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code not in RETRYABLE_STATUS:
                    raise LLMError(f"ollama rejected the request: {last_error}")
            if attempt < self._max_retries:
                time.sleep(self._backoff * (2**attempt))
        raise LLMError(f"ollama failed after retries: {last_error}")

    def _to_response(self, data: dict[str, Any], latency_ms: float) -> ModelResponse:
        message: dict[str, Any] = dict(data.get("message") or {})
        calls: list[ToolCall] = []
        stored_calls: list[dict[str, Any]] = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            arguments = fn.get("arguments")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {"_unparseable_arguments": arguments[:500]}
            if not isinstance(arguments, dict):
                arguments = {"_unparseable_arguments": str(arguments)[:500]}
            call_id = str(raw.get("id") or f"call_{secrets.token_hex(6)}")
            calls.append(
                ToolCall(call_id=call_id, name=str(fn.get("name", "")), arguments=arguments)
            )
            stored_calls.append(
                {"id": call_id, "function": {"name": fn.get("name", ""), "arguments": arguments}}
            )
        assistant: dict[str, Any] = {"role": "assistant", "content": message.get("content") or ""}
        if stored_calls:
            assistant["tool_calls"] = stored_calls
        usage = Usage(
            input_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
        )
        return ModelResponse(
            text=str(message.get("content") or "").strip(),
            tool_calls=tuple(calls),
            stop_reason=str(data.get("done_reason") or ("tool_calls" if calls else "stop")),
            usage=usage,
            model=str(data.get("model") or self._model),
            latency_ms=latency_ms,
            cost_usd=0.0,
            assistant_message=assistant,
        )
