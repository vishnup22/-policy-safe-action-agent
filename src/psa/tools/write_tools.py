"""Side-effecting tools. Called ONLY by the executor, never directly by a model.

Each handler performs one action's state change in the caller's transaction. External calls
(Stripe) carry the intent's idempotency key, so a rolled-back transaction that is retried can't
move money twice.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import IntegrityError

from psa.domain import (
    ActionIntent,
    ActionName,
    CancelOrderArgs,
    CreateTicketArgs,
    EscalateToHumanArgs,
    IssueRefundArgs,
    IssueStoreCreditArgs,
    OrderStatus,
    ScheduleFollowUpArgs,
    UpdateAddressArgs,
)
from psa.store.models import (
    FollowUpRow,
    FollowUpStatus,
    OrderRow,
    RefundRow,
    StoreCreditRow,
)
from psa.tools.context import ToolContext
from psa.tools.errors import InvalidInputError, NotFoundError


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def _order_row(ctx: ToolContext, order_id: str) -> OrderRow:
    row = ctx.db.get(OrderRow, order_id, with_for_update=True)
    if row is None:
        raise NotFoundError(f"order {order_id}")
    return row


def issue_refund(ctx: ToolContext, intent: ActionIntent) -> dict[str, Any]:
    args = intent.args
    assert isinstance(args, IssueRefundArgs)
    row = _order_row(ctx, args.order_id)
    if args.amount_cents > row.amount_paid_cents - row.amount_refunded_cents:
        # Even an unguarded system can't refund money that was never paid (processor limit).
        raise InvalidInputError("refund exceeds the amount remaining on the payment")
    receipt = ctx.payments.refund(
        payment_intent_id=row.payment_intent_id,
        amount_cents=args.amount_cents,
        idempotency_key=intent.idempotency_key,
    )
    row.amount_refunded_cents += args.amount_cents
    row.status = (
        OrderStatus.REFUNDED
        if row.amount_refunded_cents >= row.amount_paid_cents
        else OrderStatus.PARTIALLY_REFUNDED
    )
    ctx.db.add(
        RefundRow(
            refund_id=_new_id("rfd"),
            order_id=row.order_id,
            amount_cents=args.amount_cents,
            item_skus=list(args.item_skus),
            reason=args.reason,
            stripe_refund_id=receipt.refund_id,
            idempotency_key=intent.idempotency_key,
            intent_id=intent.intent_id,
            created_at=ctx.clock.now(),
        )
    )
    try:
        ctx.db.flush()
    except IntegrityError as exc:
        raise InvalidInputError("refund rejected by the system of record") from exc
    return {
        "refund_id": receipt.refund_id,
        "gateway": receipt.gateway,
        "order_id": row.order_id,
        "amount_cents": args.amount_cents,
        "order_status": row.status.value,
    }


def issue_store_credit(ctx: ToolContext, intent: ActionIntent) -> dict[str, Any]:
    args = intent.args
    assert isinstance(args, IssueStoreCreditArgs)
    if ctx.repo.get_customer(args.customer_id) is None:
        raise NotFoundError(f"customer {args.customer_id}")
    credit_id = _new_id("crd")
    ctx.db.add(
        StoreCreditRow(
            credit_id=credit_id,
            customer_id=args.customer_id,
            order_id=args.order_id,
            amount_cents=args.amount_cents,
            reason=args.reason,
            idempotency_key=intent.idempotency_key,
            intent_id=intent.intent_id,
            issued_at=ctx.clock.now(),
        )
    )
    ctx.db.flush()
    return {"credit_id": credit_id, "amount_cents": args.amount_cents}


def cancel_order(ctx: ToolContext, intent: ActionIntent) -> dict[str, Any]:
    args = intent.args
    assert isinstance(args, CancelOrderArgs)
    row = _order_row(ctx, args.order_id)
    row.status = OrderStatus.CANCELLED
    ctx.db.flush()
    return {"order_id": row.order_id, "order_status": row.status.value, "payment": "voided"}


def update_address(ctx: ToolContext, intent: ActionIntent) -> dict[str, Any]:
    args = intent.args
    assert isinstance(args, UpdateAddressArgs)
    row = _order_row(ctx, args.order_id)
    row.shipping_address = args.new_address.model_dump(mode="json")
    ctx.db.flush()
    return {"order_id": row.order_id, "shipping_address": row.shipping_address}


def create_ticket(ctx: ToolContext, intent: ActionIntent) -> dict[str, Any]:
    args = intent.args
    assert isinstance(args, CreateTicketArgs)
    return {"ticket_id": _new_id("tkt"), "subject": args.subject, "order_id": args.order_id}


def escalate_to_human(ctx: ToolContext, intent: ActionIntent) -> dict[str, Any]:
    args = intent.args
    assert isinstance(args, EscalateToHumanArgs)
    return {"handoff_id": _new_id("hnd"), "priority": args.priority.value, "queue": "support"}


def schedule_follow_up(ctx: ToolContext, intent: ActionIntent) -> dict[str, Any]:
    args = intent.args
    assert isinstance(args, ScheduleFollowUpArgs)
    follow_up_id = _new_id("fup")
    ctx.db.add(
        FollowUpRow(
            follow_up_id=follow_up_id,
            conversation_id=intent.conversation_id,
            order_id=args.order_id,
            due_at=args.due_at,
            note=args.note,
            status=FollowUpStatus.SCHEDULED,
        )
    )
    ctx.db.flush()
    return {"follow_up_id": follow_up_id, "due_at": args.due_at.isoformat()}


WRITE_TOOLS: dict[ActionName, Callable[[ToolContext, ActionIntent], dict[str, Any]]] = {
    ActionName.ISSUE_REFUND: issue_refund,
    ActionName.ISSUE_STORE_CREDIT: issue_store_credit,
    ActionName.CANCEL_ORDER: cancel_order,
    ActionName.UPDATE_ADDRESS: update_address,
    ActionName.CREATE_TICKET: create_ticket,
    ActionName.ESCALATE_TO_HUMAN: escalate_to_human,
    ActionName.SCHEDULE_FOLLOW_UP: schedule_follow_up,
}
