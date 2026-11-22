"""Per-model prices (USD per million tokens) used to report cost per conversation.

Defaults are Anthropic first-party list prices as of 2026-11-03. Override or add models with
LLM_PRICE_<MODEL_ID_UPPER_SNAKE>="<input>,<output>", e.g.
LLM_PRICE_CLAUDE_OPUS_5_5="4,20". Unknown models cost 0 (and are reported as such).
"""

from __future__ import annotations

import os

from psa.llm.types import Usage

DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-2": (8.0, 40.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25


def price_for(model: str) -> tuple[float, float] | None:
    override = os.environ.get("LLM_PRICE_" + model.upper().replace("-", "_").replace(".", "_"))
    if override:
        input_price, output_price = (float(x) for x in override.split(","))
        return input_price, output_price
    return DEFAULT_PRICES.get(model)


def cost_usd(model: str, usage: Usage) -> float:
    prices = price_for(model)
    if prices is None:
        return 0.0
    input_price, output_price = prices
    per = 1_000_000
    return (
        usage.input_tokens * input_price / per
        + usage.cache_read_input_tokens * input_price * CACHE_READ_FACTOR / per
        + usage.cache_creation_input_tokens * input_price * CACHE_WRITE_FACTOR / per
        + usage.output_tokens * output_price / per
    )
