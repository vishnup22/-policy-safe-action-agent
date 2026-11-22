"""Real model smoke test. Opt in with RUN_LIVE_LLM=1 (uses LLM_* env; paid APIs cost money)."""

from __future__ import annotations

import os

import pytest

from psa.llm import ToolSpec, client_from_env

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(
        not (os.environ.get("RUN_LIVE_LLM") == "1" and os.environ.get("LLM_MODEL")),
        reason="set RUN_LIVE_LLM=1 and LLM_MODEL (plus LLM_PROVIDER/LLM_API_KEY) to run",
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
