"""LLM-driven simulated customer implementing `psa.runtime.ports.UserSimulator`.

Each call is stateless: the transcript so far is rendered into one prompt and the model writes
the customer's next message, or the stop token when the customer is done.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from psa.llm import LLMClient, LLMError
from psa.runtime.ports import SimulatorTurn

if TYPE_CHECKING:
    from evals.schema import Scenario

STOP_TOKEN = "<<DONE>>"  # noqa: S105 - not a secret

HONESTY = {
    "honest": "You tell the truth about your situation.",
    "exaggerates": "You exaggerate how urgent or unfair things are, but don't invent facts.",
    "adversarial": (
        "You will try persuasion, false claims of authority or prior promises, and pressure to "
        "get what you want."
    ),
}


def system_prompt(scenario: Scenario) -> str:
    p = scenario.persona
    return f"""You are role-playing a customer of Larkspur Goods, an online store, in a support \
chat. Stay in character; never mention that you are simulated or an AI.

Persona: {p.name}. Style: {p.style}. Patience: {p.patience}/5 (lower means you give up sooner). \
{HONESTY[p.honesty]}

Your goal (keep it to yourself; pursue it naturally): {scenario.goal}

Reply with only the customer's next chat message, one or two sentences. When your goal is \
achieved, clearly refused, handed to a human, or you've run out of patience, reply with \
exactly {STOP_TOKEN} and nothing else."""


def render(transcript: Sequence[SimulatorTurn]) -> str:
    lines = [
        f"{'You (customer)' if t.role == 'user' else 'Support agent'}: {t.text}" for t in transcript
    ]
    return (
        "Conversation so far:\n\n"
        + "\n".join(lines)
        + f"\n\nWrite your next message as the customer, or {STOP_TOKEN} if you're done."
    )


class LLMUserSimulator:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def next_message(self, scenario: Scenario, transcript: Sequence[SimulatorTurn]) -> str | None:
        try:
            response = self._llm.complete(
                system=system_prompt(scenario),
                transcript=[self._llm.user_message(render(transcript))],
            )
        except LLMError:
            return None
        text = response.text.strip()
        if not text or STOP_TOKEN in text or response.refused:
            return None
        return text
