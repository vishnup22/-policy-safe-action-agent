"""JSON-schema helpers for tool definitions (inline $refs so every provider accepts them)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from psa.domain import (
    ActionName,
    CancelOrderArgs,
    CreateTicketArgs,
    EscalateToHumanArgs,
    IssueRefundArgs,
    IssueStoreCreditArgs,
    ScheduleFollowUpArgs,
    UpdateAddressArgs,
)

ARGS_MODELS: dict[ActionName, type[BaseModel]] = {
    ActionName.ISSUE_REFUND: IssueRefundArgs,
    ActionName.ISSUE_STORE_CREDIT: IssueStoreCreditArgs,
    ActionName.CANCEL_ORDER: CancelOrderArgs,
    ActionName.UPDATE_ADDRESS: UpdateAddressArgs,
    ActionName.CREATE_TICKET: CreateTicketArgs,
    ActionName.ESCALATE_TO_HUMAN: EscalateToHumanArgs,
    ActionName.SCHEDULE_FOLLOW_UP: ScheduleFollowUpArgs,
}

ACTION_DESCRIPTIONS: dict[ActionName, str] = {
    ActionName.ISSUE_REFUND: "Refund money to the original payment method for an order.",
    ActionName.ISSUE_STORE_CREDIT: "Add store credit to a customer account.",
    ActionName.CANCEL_ORDER: "Cancel an order.",
    ActionName.UPDATE_ADDRESS: "Change an order's shipping address.",
    ActionName.CREATE_TICKET: "Open a support ticket for follow-up by the team.",
    ActionName.ESCALATE_TO_HUMAN: "Hand the conversation to a human agent.",
    ActionName.SCHEDULE_FOLLOW_UP: "Schedule a follow-up check-in at a future time (ISO-8601).",
}


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return _inline(defs[ref.removeprefix("#/$defs/")], defs)
        return {k: _inline(v, defs) for k, v in node.items() if k not in {"$defs", "title"}}
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def args_schema(action: ActionName) -> dict[str, Any]:
    """Input schema for an action's arguments, without the `action` discriminator."""
    raw = ARGS_MODELS[action].model_json_schema()
    schema: dict[str, Any] = _inline(raw, raw.get("$defs", {}))
    schema["properties"].pop("action", None)
    schema["required"] = [r for r in schema.get("required", []) if r != "action"]
    return schema
