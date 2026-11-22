"""Real provider smoke test. Skipped unless LLM_API_KEY and LLM_MODEL are set (costs money)."""

from __future__ import annotations

import os

import pytest

from psa.llm import ToolSpec, client_from_env

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not (os.environ.get("LLM_API_KEY") and os.environ.get("LLM_MODEL")),
        reason="set LLM_API_KEY and LLM_MODEL to run live LLM tests",
    ),
]


def test_live_tool_call_round_trip() -> None:
    llm = client_from_env()
    tool = ToolSpec(
        name="get_order",
        description="Look up an order by id.",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )
    first = llm.complete(
        system="You are a support agent. Use tools to look things up.",
        transcript=[llm.user_message("What's the status of order ord_000123?")],
        tools=[tool],
    )
    assert first.tool_calls, "expected the model to call get_order"
    assert first.tool_calls[0].arguments.get("order_id") == "ord_000123"
    assert first.usage.input_tokens > 0
