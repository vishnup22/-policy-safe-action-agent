"""Baseline and guarded agents.

Both share the read tools, the turn loop and identical event logging, so eval metrics compare
like with like. The ONLY difference is how a side effect is requested:

- Baseline: one tool per action, executed directly (policy is just text in the prompt).
- Guarded: a single `propose_action` tool; every proposal goes through `psa.policy.decide()`.

Event-log invariant relied on by the eval judge: every ACTION_EXECUTED is preceded by an
ACTION_PROPOSED carrying the full intent with the same intent_id (for both agents).
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import TypeAdapter, ValidationError

from psa.clock import Clock
from psa.domain import (
    ActionArgs,
    ActionIntent,
    ActionName,
    Decision,
    DecisionOutcome,
    EventType,
)
from psa.executor import Executor, request_approval
from psa.llm import LLMClient, ModelResponse, ToolCall, ToolOutput, ToolSpec
from psa.policy import PolicySet, decide
from psa.store import EventLog
from psa.tools import READ_TOOLS, ToolContext, ToolFailure

from . import prompts
from .loop import TurnState, run_turn
from .schemas import ACTION_DESCRIPTIONS, args_schema

_ARGS = TypeAdapter(ActionArgs)
PROPOSE_ACTION = "propose_action"


def idempotency_key(conversation_id: str, args: Any) -> str:
    """Same conversation + same action + same arguments => same key (no double refunds)."""
    canonical = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(f"{conversation_id}|{canonical}".encode()).hexdigest()[:32]
    return f"idem_{digest}"


def make_intent(
    *, conversation_id: str, customer_id: str | None, args: Any, justification: str, clock: Clock
) -> ActionIntent:
    return ActionIntent(
        intent_id=f"int_{secrets.token_hex(8)}",
        conversation_id=conversation_id,
        customer_id=customer_id,
        args=args,
        justification=(justification or "(none given)")[:1000],
        proposed_at=clock.now(),
        idempotency_key=idempotency_key(conversation_id, args),
    )


def _json(data: Any) -> str:
    return json.dumps(data, default=str, separators=(",", ":"))


@dataclass
class TurnResultInternal:
    state: TurnState
    pending_approval_id: str | None


@dataclass
class _AgentBase:
    llm: LLMClient
    ctx: ToolContext
    log: EventLog
    executor: Executor
    policy: PolicySet
    max_steps: int
    pending_approval_id: str | None = field(default=None, init=False)

    @property
    def clock(self) -> Clock:
        return self.ctx.clock

    @property
    def conversation_id(self) -> str:
        return self.ctx.session.conversation_id

    # ---- overridden by subclasses
    def system_prompt(self) -> str:
        raise NotImplementedError

    def action_tools(self) -> list[ToolSpec]:
        raise NotImplementedError

    def dispatch_action(self, call: ToolCall) -> dict[str, Any]:
        raise NotImplementedError

    # ---- shared
    def tools(self) -> list[ToolSpec]:
        return [t.spec for t in READ_TOOLS.values()] + self.action_tools()

    def run(self, transcript: list[Any]) -> TurnResultInternal:
        state = run_turn(
            llm=self.llm,
            system=self.system_prompt(),
            tools=self.tools(),
            transcript=transcript,
            dispatch=self._dispatch,
            on_response=self._record_model_call,
            max_steps=self.max_steps,
        )
        return TurnResultInternal(state=state, pending_approval_id=self.pending_approval_id)

    def _record_model_call(self, response: ModelResponse) -> None:
        self.log.append(
            self.conversation_id,
            EventType.MODEL_CALL,
            at=self.clock.now(),
            payload={
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_ms": round(response.latency_ms, 2),
                "cost_usd": round(response.cost_usd, 6),
            },
        )

    def _dispatch(self, call: ToolCall) -> ToolOutput:
        self.log.append(
            self.conversation_id,
            EventType.TOOL_CALL,
            at=self.clock.now(),
            payload={"call_id": call.call_id, "tool": call.name, "args": call.arguments},
        )
        started = time.perf_counter()
        ok, result, error = True, None, None
        try:
            if call.name in READ_TOOLS:
                tool = READ_TOOLS[call.name]
                self.ctx.faults.before_call(call.name)
                result = tool.run(self.ctx, tool.input_model.model_validate(call.arguments))
            else:
                result = self.dispatch_action(call)
        except ValidationError as exc:
            ok, error = False, f"invalid arguments: {exc.errors(include_url=False)}"
        except ToolFailure as exc:
            ok, error = False, f"{exc.code}: {exc.message}"
        latency = round((time.perf_counter() - started) * 1000, 2)
        self.log.append(
            self.conversation_id,
            EventType.TOOL_RESULT,
            at=self.clock.now(),
            payload={
                "call_id": call.call_id,
                "ok": ok,
                "result": result,
                "error": error,
                "latency_ms": latency,
            },
        )
        content = _json(result) if ok else _json({"error": error})
        return ToolOutput(call_id=call.call_id, content=content, is_error=not ok)

    def _propose(self, args: Any, justification: str) -> ActionIntent:
        intent = make_intent(
            conversation_id=self.conversation_id,
            customer_id=self.ctx.session.customer_id,
            args=args,
            justification=justification,
            clock=self.clock,
        )
        self.log.append(
            self.conversation_id,
            EventType.ACTION_PROPOSED,
            at=self.clock.now(),
            payload={"intent": intent.model_dump(mode="json")},
        )
        return intent

    def _execute(self, intent: ActionIntent) -> dict[str, Any]:
        result = self.executor.execute(
            intent, ctx=self.ctx, log=self.log, policy_version=self.policy.version
        )
        return result.for_model()


@dataclass
class BaselineAgent(_AgentBase):
    """Policy lives only in the prompt; action tools execute immediately."""

    def system_prompt(self) -> str:
        return prompts.baseline_prompt(self.policy)

    def action_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=a.value, description=ACTION_DESCRIPTIONS[a], input_schema=args_schema(a))
            for a in ActionName
        ]

    def dispatch_action(self, call: ToolCall) -> dict[str, Any]:
        try:
            action = ActionName(call.name)
        except ValueError as exc:
            raise ToolFailure("unknown_tool", f"no tool named {call.name}") from exc
        args = _ARGS.validate_python({**call.arguments, "action": action.value})
        intent = self._propose(args, justification="baseline direct tool call")
        return self._execute(intent)


@dataclass
class GuardedAgent(_AgentBase):
    """Every side effect is a proposal, decided by the policy engine before execution.

    The model sees the SAME action tools as the baseline (one per action, same schemas), so
    the only difference between the two systems is enforcement. Each call here creates a
    proposal; nothing executes unless the policy engine allows it. A generic
    `propose_action(action, args, justification)` is also accepted (used by the MCP server).
    """

    def system_prompt(self) -> str:
        return prompts.GUARDED

    def action_tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=a.value,
                description=ACTION_DESCRIPTIONS[a] + " Subject to store policy; may be denied, "
                "need identity verification, or need a team member's approval.",
                input_schema=args_schema(a),
            )
            for a in ActionName
        ]

    def dispatch_action(self, call: ToolCall) -> dict[str, Any]:
        if call.name == PROPOSE_ACTION:
            raw_args = call.arguments.get("args") or {}
            action = call.arguments.get("action")
            justification = str(call.arguments.get("justification", ""))
            if not isinstance(raw_args, dict) or not isinstance(action, str):
                raise ToolFailure(
                    "invalid_input", "propose_action needs `action` and an `args` object"
                )
        else:
            try:
                action = ActionName(call.name).value
            except ValueError as exc:
                raise ToolFailure("unknown_tool", f"no tool named {call.name}") from exc
            raw_args = {k: v for k, v in call.arguments.items() if k != "justification"}
            justification = str(call.arguments.get("justification", "")) or "model request"
        args = _ARGS.validate_python({**raw_args, "action": action})
        intent = self._propose(args, justification)
        decision = decide(
            intent, self.policy, session=self.ctx.session, source=self.ctx.repo, clock=self.clock
        )
        self.log.append(
            self.conversation_id,
            EventType.POLICY_DECISION,
            at=self.clock.now(),
            policy_version=decision.policy_version,
            payload={"decision": decision.model_dump(mode="json")},
        )
        return self._act_on(intent, decision)

    def _act_on(self, intent: ActionIntent, decision: Decision) -> dict[str, Any]:
        messages = [r.message for r in decision.deciding_rules]
        base: dict[str, Any] = {
            "decision": decision.outcome.value,
            "reason_codes": [c.value for c in decision.reason_codes],
            "messages_for_customer": messages,
        }
        match decision.outcome:
            case DecisionOutcome.ALLOW:
                return {**base, "messages_for_customer": [], "execution": self._execute(intent)}
            case DecisionOutcome.REQUIRE_APPROVAL:
                approval_id = request_approval(self.ctx.db, self.log, self.clock, intent, decision)
                self.pending_approval_id = approval_id
                return {**base, "approval_id": approval_id, "status": "pending_human_review"}
            case DecisionOutcome.REQUIRE_VERIFICATION:
                self.log.append(
                    self.conversation_id,
                    EventType.VERIFICATION_REQUESTED,
                    at=self.clock.now(),
                    payload={"intent_id": intent.intent_id, "reason_codes": base["reason_codes"]},
                )
                return {**base, "status": "verification_required"}
            case DecisionOutcome.DENY:
                return {**base, "status": "denied"}
