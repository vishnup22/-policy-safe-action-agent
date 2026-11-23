"""Anthropic adapter: request shape and response mapping, with a fake SDK client (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from psa.llm import ToolOutput, ToolSpec
from psa.llm.anthropic_client import FALLBACK_BETA, AnthropicClient
from psa.llm.pricing import cost_usd
from psa.llm.types import Usage


class _Block:
    def __init__(self, **data: Any) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class _Endpoint:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def _response(*blocks: _Block, stop: str = "tool_use", model: str = "claude-opus-5-5") -> Any:
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop,
        model=model,
        usage=SimpleNamespace(
            input_tokens=1000,
            output_tokens=500,
            cache_read_input_tokens=None,
            cache_creation_input_tokens=None,
        ),
    )


def _client(response: Any, **kwargs: Any) -> tuple[AnthropicClient, _Endpoint, _Endpoint]:
    beta, plain = _Endpoint(response), _Endpoint(response)
    fake = SimpleNamespace(beta=SimpleNamespace(messages=beta), messages=plain)
    return AnthropicClient(model="claude-opus-5-5", client=fake, **kwargs), beta, plain  # type: ignore[arg-type]


TOOL = ToolSpec(name="get_order", description="d", input_schema={"type": "object"})


def test_request_shape_uses_fallbacks_effort_and_auto_tool_choice() -> None:
    client, beta, plain = _client(_response(_Block(type="text", text="hi"), stop="end_turn"))
    client.complete(system="sys", transcript=[client.user_message("hello")], tools=[TOOL])
    assert plain.kwargs is None
    kwargs = beta.kwargs
    assert kwargs is not None
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["system"] == "sys"
    assert kwargs["betas"] == [FALLBACK_BETA]
    assert kwargs["fallbacks"] == "default"
    assert kwargs["output_config"] == {"effort": "medium"}
    assert "tool_choice" not in kwargs  # forcing a tool 400s on current models
    assert "thinking" not in kwargs  # model default (adaptive)
    assert kwargs["tools"] == [
        {"name": "get_order", "description": "d", "input_schema": {"type": "object"}}
    ]
    assert kwargs["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]


def test_fallbacks_off_uses_plain_endpoint() -> None:
    client, beta, plain = _client(
        _response(_Block(type="text", text="x"), stop="end_turn"), fallbacks="off"
    )
    client.complete(system="s", transcript=[client.user_message("q")])
    assert beta.kwargs is None
    assert plain.kwargs is not None
    assert "betas" not in plain.kwargs


def test_response_mapping_keeps_assistant_content_unchanged() -> None:
    thinking = _Block(type="thinking", thinking="", signature="sig123")
    text = _Block(type="text", text="Let me check.")
    call = _Block(type="tool_use", id="toolu_1", name="get_order", input={"order_id": "ord_000001"})
    client, _, _ = _client(_response(thinking, text, call))
    response = client.complete(system="s", transcript=[client.user_message("q")], tools=[TOOL])
    assert response.text == "Let me check."
    assert [(c.call_id, c.name, c.arguments) for c in response.tool_calls] == [
        ("toolu_1", "get_order", {"order_id": "ord_000001"})
    ]
    # Thinking blocks (with signatures) must be resent unchanged on the next request.
    assert response.assistant_message == {
        "role": "assistant",
        "content": [thinking.to_dict(), text.to_dict(), call.to_dict()],
    }
    assert response.cost_usd == pytest.approx(0.004 + 0.01)
    assert response.usage.input_tokens == 1000


def test_refusal_is_flagged() -> None:
    client, _, _ = _client(_response(stop="refusal"))
    assert client.complete(system="s", transcript=[client.user_message("q")]).refused


def test_tool_results_go_back_in_one_user_message() -> None:
    client, _, _ = _client(_response())
    message = client.tool_results_message(
        [ToolOutput(call_id="a", content="{}"), ToolOutput(call_id="b", content="x", is_error=True)]
    )
    assert message["role"] == "user"
    assert [b["tool_use_id"] for b in message["content"]] == ["a", "b"]
    assert message["content"][1]["is_error"] is True


@pytest.mark.parametrize("kwargs", [{"model": ""}, {"model": "m", "fallbacks": "maybe"}])
def test_bad_configuration_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        AnthropicClient(client=SimpleNamespace(), **kwargs)  # type: ignore[arg-type]


def test_pricing_override_and_unknown_model(monkeypatch: pytest.MonkeyPatch) -> None:
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost_usd("unknown-model", usage) == 0.0
    monkeypatch.setenv("LLM_PRICE_MY_MODEL", "1,2")
    assert cost_usd("my-model", usage) == pytest.approx(3.0)
    cached = Usage(cache_read_input_tokens=1_000_000)
    assert cost_usd("claude-opus-5-5", cached) == pytest.approx(0.4)


def test_client_from_env_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from psa.llm import LLMError, client_from_env

    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(LLMError, match="unsupported"):
        client_from_env()
