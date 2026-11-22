"""Native Ollama adapter — offline tests with a mock transport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from psa.llm import LLMError, ToolOutput, ToolSpec, client_from_env
from psa.llm.ollama_client import OllamaClient

TOOL = ToolSpec(name="get_order", description="Look up", input_schema={"type": "object"})


def _reply(message: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "model": "qwen2.5:14b",
        "message": message,
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 2400,
        "eval_count": 60,
        **extra,
    }


class _Server:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.paths: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        self.requests.append(json.loads(request.content))
        return self.responses.pop(0)


def _client(server: _Server, **kwargs: Any) -> OllamaClient:
    http = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(server))
    return OllamaClient(model="qwen2.5:14b", http=http, retry_backoff_s=0, **kwargs)


def test_uses_native_chat_with_context_window() -> None:
    server = _Server(httpx.Response(200, json=_reply({"role": "assistant", "content": "Hi"})))
    client = _client(server, num_ctx=16384, temperature=0.0)
    response = client.complete(system="s", transcript=[client.user_message("hello")], tools=[TOOL])
    assert server.paths == ["/api/chat"]
    body = server.requests[0]
    assert body["options"] == {"num_ctx": 16384, "temperature": 0.0}
    assert body["stream"] is False
    assert body["tools"][0]["function"]["name"] == "get_order"
    assert response.usage.input_tokens == 2400
    assert response.cost_usd == 0.0


def test_tool_call_round_trip_with_tool_names() -> None:
    call = {"function": {"name": "get_order", "arguments": {"order_id": "ord_1"}}}
    server = _Server(
        httpx.Response(
            200, json=_reply({"role": "assistant", "content": "", "tool_calls": [call]})
        ),
        httpx.Response(200, json=_reply({"role": "assistant", "content": "Shipped."})),
    )
    client = _client(server)
    first = client.complete(system="s", transcript=[client.user_message("where")], tools=[TOOL])
    (tool_call,) = first.tool_calls
    assert tool_call.arguments == {"order_id": "ord_1"}
    batch = client.tool_results_message([ToolOutput(call_id=tool_call.call_id, content="{}")])
    client.complete(
        system="s",
        transcript=[client.user_message("where"), first.assistant_message, batch],
        tools=[TOOL],
    )
    sent = server.requests[1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool"]
    assert sent[3] == {"role": "tool", "content": "{}", "tool_name": "get_order"}


def test_string_arguments_and_garbage_are_handled() -> None:
    calls = [
        {"function": {"name": "a", "arguments": '{"x": 1}'}},
        {"function": {"name": "b", "arguments": "not json"}},
    ]
    server = _Server(httpx.Response(200, json=_reply({"role": "assistant", "tool_calls": calls})))
    response = _client(server).complete(system="s", transcript=[{"role": "user", "content": "q"}])
    assert response.tool_calls[0].arguments == {"x": 1}
    assert "_unparseable_arguments" in response.tool_calls[1].arguments


def test_strips_v1_suffix_from_base_url() -> None:
    client = OllamaClient(model="m", base_url="http://localhost:11434/v1")
    assert str(client._http.base_url).rstrip("/") == "http://localhost:11434"


def test_unreachable_server_is_a_clear_error() -> None:
    def refuse(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    http = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(refuse))
    client = OllamaClient(model="m", http=http, max_retries=0)
    with pytest.raises(LLMError, match="is it running"):
        client.complete(system="s", transcript=[{"role": "user", "content": "q"}])


def test_model_not_found_is_not_retried() -> None:
    server = _Server(httpx.Response(404, text='{"error":"model not found, try pulling it"}'))
    with pytest.raises(LLMError, match="model not found"):
        _client(server).complete(system="s", transcript=[{"role": "user", "content": "q"}])
    assert len(server.requests) == 1


def test_retries_then_succeeds() -> None:
    server = _Server(
        httpx.Response(503, text="busy"),
        httpx.Response(200, json=_reply({"role": "assistant", "content": "ok"})),
    )
    assert (
        _client(server).complete(system="s", transcript=[{"role": "user", "content": "q"}]).text
        == "ok"
    )


def test_env_selects_native_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:14b")
    monkeypatch.setenv("LLM_NUM_CTX", "8192")
    client = client_from_env()
    assert isinstance(client, OllamaClient)
    assert client._num_ctx == 8192


def test_model_required() -> None:
    with pytest.raises(ValueError, match="LLM_MODEL"):
        OllamaClient(model="")
