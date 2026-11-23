"""OpenAI-compatible adapter (Ollama, LM Studio, vLLM, OpenRouter, Groq, HF) — offline tests."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from psa.llm import LLMError, ToolOutput, ToolSpec, client_from_env
from psa.llm.openai_compat import TOOL_BATCH, OpenAICompatibleClient

TOOL = ToolSpec(name="get_order", description="Look up", input_schema={"type": "object"})


def _completion(
    message: dict[str, Any], finish: str = "stop", model: str = "qwen2.5:14b"
) -> dict[str, Any]:
    return {
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }


class _Server:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.headers: list[httpx.Headers] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        self.headers.append(request.headers)
        return self.responses.pop(0)


def _client(server: _Server, **kwargs: Any) -> OpenAICompatibleClient:
    http = httpx.Client(base_url="http://model.test/v1", transport=httpx.MockTransport(server))
    return OpenAICompatibleClient(
        model="qwen2.5:14b", base_url="http://model.test/v1", http=http, retry_backoff_s=0, **kwargs
    )


def test_request_shape() -> None:
    server = _Server(httpx.Response(200, json=_completion({"role": "assistant", "content": "Hi"})))
    client = _client(server, temperature=0.0)
    client.complete(system="be nice", transcript=[client.user_message("hello")], tools=[TOOL])
    body = server.requests[0]
    assert body["model"] == "qwen2.5:14b"
    assert body["messages"] == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hello"},
    ]
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "get_order",
                "description": "Look up",
                "parameters": {"type": "object"},
            },
        }
    ]
    assert body["tool_choice"] == "auto"
    assert body["temperature"] == 0.0
    assert body["stream"] is False


def test_tool_calls_parsed_and_round_tripped() -> None:
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "get_order", "arguments": '{"order_id": "ord_1"}'},
    }
    server = _Server(
        httpx.Response(
            200,
            json=_completion(
                {"role": "assistant", "content": None, "tool_calls": [call]}, "tool_calls"
            ),
        ),
        httpx.Response(200, json=_completion({"role": "assistant", "content": "It shipped."})),
    )
    client = _client(server)
    first = client.complete(system="s", transcript=[client.user_message("where?")], tools=[TOOL])
    assert [(c.call_id, c.name, c.arguments) for c in first.tool_calls] == [
        ("c1", "get_order", {"order_id": "ord_1"})
    ]
    assert first.usage.input_tokens == 120
    assert first.cost_usd == 0.0  # open/local models are free unless priced via env

    results = client.tool_results_message(
        [ToolOutput(call_id="c1", content='{"status":"shipped"}')]
    )
    assert results["role"] == TOOL_BATCH
    transcript = [client.user_message("where?"), first.assistant_message, results]
    second = client.complete(system="s", transcript=transcript, tools=[TOOL])
    assert second.text == "It shipped."
    sent = server.requests[1]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool"]
    assert sent[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"status":"shipped"}'}
    assert sent[2]["tool_calls"][0]["function"]["arguments"] == '{"order_id": "ord_1"}'


def test_error_results_are_marked() -> None:
    client = _client(_Server())
    batch = client.tool_results_message([ToolOutput(call_id="x", content="boom", is_error=True)])
    assert batch["messages"][0]["content"] == "ERROR: boom"


def test_object_arguments_and_missing_ids_are_tolerated() -> None:
    call = {"function": {"name": "get_order", "arguments": {"order_id": "ord_2"}}}
    server = _Server(
        httpx.Response(
            200, json=_completion({"role": "assistant", "content": "", "tool_calls": [call]})
        )
    )
    client = _client(server)
    response = client.complete(system="s", transcript=[client.user_message("q")], tools=[TOOL])
    assert response.tool_calls[0].arguments == {"order_id": "ord_2"}
    assert response.tool_calls[0].call_id.startswith("call_0_")


def test_unparseable_arguments_surface_as_bad_input_not_a_crash() -> None:
    call = {"id": "c9", "function": {"name": "get_order", "arguments": "{order_id: ord_3"}}
    server = _Server(
        httpx.Response(200, json=_completion({"role": "assistant", "tool_calls": [call]}))
    )
    client = _client(server)
    response = client.complete(system="s", transcript=[client.user_message("q")], tools=[TOOL])
    assert "_unparseable_arguments" in response.tool_calls[0].arguments


def test_retries_transient_errors_then_succeeds() -> None:
    server = _Server(
        httpx.Response(503, text="loading model"),
        httpx.Response(429, text="slow down"),
        httpx.Response(200, json=_completion({"role": "assistant", "content": "ok"})),
    )
    response = _client(server, max_retries=3).complete(
        system="s", transcript=[{"role": "user", "content": "q"}]
    )
    assert response.text == "ok"
    assert len(server.requests) == 3


def test_non_retryable_error_raises_immediately() -> None:
    server = _Server(httpx.Response(400, text="model does not support tools"))
    with pytest.raises(LLMError, match="does not support tools"):
        _client(server).complete(system="s", transcript=[{"role": "user", "content": "q"}])
    assert len(server.requests) == 1


def test_gives_up_after_retries() -> None:
    server = _Server(*[httpx.Response(500, text="oops")] * 3)
    with pytest.raises(LLMError, match="failed after retries"):
        _client(server, max_retries=2).complete(
            system="s", transcript=[{"role": "user", "content": "q"}]
        )


def test_connection_error_is_an_llm_error() -> None:
    def refuse(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    http = httpx.Client(base_url="http://model.test/v1", transport=httpx.MockTransport(refuse))
    client = OpenAICompatibleClient(
        model="m", base_url="http://model.test/v1", http=http, max_retries=0
    )
    with pytest.raises(LLMError, match="could not reach"):
        client.complete(system="s", transcript=[{"role": "user", "content": "q"}])


def test_api_key_sent_as_bearer_when_configured() -> None:
    server = _Server(httpx.Response(200, json=_completion({"role": "assistant", "content": "x"})))
    http = httpx.Client(
        base_url="http://model.test/v1",
        transport=httpx.MockTransport(server),
        headers={"Authorization": "Bearer sk-or-test"},
    )
    client = OpenAICompatibleClient(
        model="m", base_url="http://model.test/v1", http=http, api_key="sk-or-test"
    )
    client.complete(system="s", transcript=[{"role": "user", "content": "q"}])
    assert server.headers[0]["authorization"] == "Bearer sk-or-test"


def test_empty_choices_is_an_error() -> None:
    server = _Server(httpx.Response(200, json={"choices": []}))
    with pytest.raises(LLMError, match="no choices"):
        _client(server).complete(system="s", transcript=[{"role": "user", "content": "q"}])


@pytest.mark.parametrize(
    ("provider", "url"),
    [
        ("ollama_openai", "http://localhost:11434/v1"),
        ("openrouter", "https://openrouter.ai/api/v1"),
        ("groq", "https://api.groq.com/openai/v1"),
        ("huggingface", "https://router.huggingface.co/v1"),
    ],
)
def test_client_from_env_providers(
    monkeypatch: pytest.MonkeyPatch, provider: str, url: str
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_MODEL", "some-model")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    client = client_from_env()
    assert isinstance(client, OpenAICompatibleClient)
    assert client.provider == provider
    assert str(client._http.base_url).rstrip("/") == url


def test_custom_base_url_required_for_generic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compat")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        client_from_env()


def test_default_provider_is_native_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    from psa.llm.ollama_client import OllamaClient

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:14b")
    assert isinstance(client_from_env(), OllamaClient)
