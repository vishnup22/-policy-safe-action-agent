"""Deterministic, network-free LLM for tests and demos.

A script is a function `(system, transcript, tools) -> Step`; ScriptedLLM turns each Step into a
ModelResponse in a simple native format:
    {"role": "user", "text": ...}
    {"role": "assistant", "text": ..., "tool_calls": [{"id", "name", "arguments"}]}
    {"role": "tool", "results": [{"call_id", "content", "is_error"}]}
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from psa.llm.types import ModelResponse, NativeMessage, ToolCall, ToolOutput, ToolSpec, Usage


@dataclass(frozen=True)
class Step:
    text: str = ""
    tool_calls: tuple[tuple[str, dict[str, Any]], ...] = ()


Script = Callable[[str, Sequence[NativeMessage], Sequence[ToolSpec]], Step]


@dataclass
class ScriptedLLM:
    script: Script
    model_name: str = "scripted-llm"
    calls: list[Sequence[NativeMessage]] = field(default_factory=list[Sequence[NativeMessage]])
    tools_offered: list[list[str]] = field(default_factory=list[list[str]])

    @classmethod
    def from_steps(cls, steps: Sequence[Step]) -> ScriptedLLM:
        """Replay steps in order across all calls; afterwards reply with an empty final turn."""
        queue = list(steps)

        def script(_s: str, _t: Sequence[NativeMessage], _tools: Sequence[ToolSpec]) -> Step:
            return queue.pop(0) if queue else Step(text="Is there anything else I can help with?")

        return cls(script=script)

    @property
    def provider(self) -> str:
        return "scripted"

    @property
    def model(self) -> str:
        return self.model_name

    def user_message(self, text: str) -> NativeMessage:
        return {"role": "user", "text": text}

    def tool_results_message(self, outputs: Sequence[ToolOutput]) -> NativeMessage:
        return {"role": "tool", "results": [o.model_dump() for o in outputs]}

    def complete(
        self,
        *,
        system: str,
        transcript: Sequence[NativeMessage],
        tools: Sequence[ToolSpec] = (),
    ) -> ModelResponse:
        self.calls.append(list(transcript))
        self.tools_offered.append([t.name for t in tools])
        step = self.script(system, transcript, tools)
        n = len(self.calls)
        calls = tuple(
            ToolCall(call_id=f"call_{n}_{i}", name=name, arguments=args)
            for i, (name, args) in enumerate(step.tool_calls)
        )
        return ModelResponse(
            text=step.text,
            tool_calls=calls,
            stop_reason="tool_use" if calls else "end_turn",
            usage=Usage(input_tokens=100, output_tokens=20),
            model=self.model_name,
            latency_ms=1.0,
            cost_usd=0.0,
            assistant_message={
                "role": "assistant",
                "text": step.text,
                "tool_calls": [c.model_dump() for c in calls],
            },
        )


def last_tool_results(transcript: Sequence[NativeMessage]) -> list[dict[str, Any]]:
    """Helper for scripts: the most recent tool results, decoded when JSON."""
    import json

    for message in reversed(transcript):
        if message.get("role") == "tool":
            out: list[dict[str, Any]] = []
            for r in message["results"]:
                try:
                    content = json.loads(r["content"])
                except (TypeError, ValueError):
                    content = r["content"]
                out.append({"content": content, "is_error": r["is_error"]})
            return out
        if message.get("role") == "user":
            return []
    return []
