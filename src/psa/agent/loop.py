"""One user turn as a LangGraph state machine: model -> tools -> model ... -> reply.

The graph is the same for both agents; they differ only in tool set and dispatcher.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from psa.llm import LLMClient, ModelResponse, NativeMessage, ToolCall, ToolOutput, ToolSpec

STEP_LIMIT_REPLY = (
    "I'm sorry, this is taking longer than it should. I've stopped here so a team member can "
    "help; would you like me to open a ticket?"
)
REFUSAL_REPLY = "I'm sorry, I can't help with that request. Is there something else I can do?"
EMPTY_REPLY = "Is there anything else I can help you with?"


class TurnState(TypedDict):
    transcript: list[NativeMessage]
    pending: list[ToolCall]
    steps: int
    reply: str
    done: bool


def run_turn(
    *,
    llm: LLMClient,
    system: str,
    tools: Sequence[ToolSpec],
    transcript: list[NativeMessage],
    dispatch: Callable[[ToolCall], ToolOutput],
    on_response: Callable[[ModelResponse], None],
    max_steps: int,
) -> TurnState:
    def model_node(state: TurnState) -> TurnState:
        response = llm.complete(system=system, transcript=state["transcript"], tools=tools)
        on_response(response)
        transcript = [*state["transcript"], response.assistant_message]
        if response.refused:
            return {
                **state,
                "transcript": transcript,
                "pending": [],
                "reply": REFUSAL_REPLY,
                "done": True,
            }
        if not response.tool_calls:
            reply = response.text or EMPTY_REPLY
            return {**state, "transcript": transcript, "pending": [], "reply": reply, "done": True}
        return {**state, "transcript": transcript, "pending": list(response.tool_calls)}

    def tools_node(state: TurnState) -> TurnState:
        outputs = [dispatch(call) for call in state["pending"]]
        transcript = [*state["transcript"], llm.tool_results_message(outputs)]
        steps = state["steps"] + 1
        if steps >= max_steps:
            return {
                **state,
                "transcript": transcript,
                "pending": [],
                "steps": steps,
                "reply": STEP_LIMIT_REPLY,
                "done": True,
            }
        return {**state, "transcript": transcript, "pending": [], "steps": steps}

    def after(state: TurnState) -> str:
        return END if state["done"] else "next"

    graph: StateGraph[TurnState] = StateGraph(TurnState)
    graph.add_node("model", model_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", after, {"next": "tools", END: END})
    graph.add_conditional_edges("tools", after, {"next": "model", END: END})
    initial: TurnState = {
        "transcript": transcript,
        "pending": [],
        "steps": 0,
        "reply": "",
        "done": False,
    }
    final = graph.compile().invoke(initial, config={"recursion_limit": 2 * max_steps + 4})
    return final  # type: ignore[return-value]
