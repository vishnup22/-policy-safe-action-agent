"""Verify a conversation's identity against the stored customer and order.

Contract (see `psa.domain.verification`):

    verify_identity(db, conversation_id, args, *, clock, log) -> VerificationResult

- Looks up `args.order_id`; verified iff the order exists AND its customer's email
  matches `args.email` (case-insensitive, trimmed) AND the order's shipping postal code
  matches `args.postal_code` (case/space-insensitive). Facts come from the DB only.
- At most `MAX_VERIFICATION_ATTEMPTS` failed attempts per conversation; after that it
  returns verified=False, attempts_remaining=0 without checking.
- Appends exactly one `verification_completed` event per attempt:
  {verified, method, order_id, customer_id|null, attempts_remaining}. It does NOT append
  `verification_requested` — the guarded agent already does that (payload
  {intent_id, reason_codes}) when policy returns REQUIRE_VERIFICATION.
- Counts failed attempts from this conversation's `verification_completed` events.
- On success sets ConversationRow.customer_id and identity_verified=True. It never
  un-verifies and never switches an already-verified conversation to another customer
  (returns verified=False for a different customer).
- The message never says which field was wrong.
"""

from sqlalchemy.orm import Session

from psa.clock import Clock
from psa.domain import (
    MAX_VERIFICATION_ATTEMPTS,
    EventType,
    VerificationMethod,
    VerificationResult,
    VerifyIdentityArgs,
)
from psa.store import CommerceRepo, EventLog, UnknownConversationError
from psa.store.models import ConversationRow


def _matching_customer(repo: CommerceRepo, args: VerifyIdentityArgs) -> str | None:
    order = repo.get_order(args.order_id)
    if order is None:
        return None
    customer = repo.get_customer(order.customer_id)
    if customer is None or customer.email.strip().casefold() != args.email.strip().casefold():
        return None
    stored_postal = "".join(order.shipping_address.postal_code.split()).casefold()
    supplied_postal = "".join(args.postal_code.split()).casefold()
    return customer.customer_id if stored_postal == supplied_postal else None


def verify_identity(
    db: Session, conversation_id: str, args: VerifyIdentityArgs, *, clock: Clock, log: EventLog
) -> VerificationResult:
    # Hold the same row lock used by EventLog so attempts and identity changes serialize.
    conversation = db.get(
        ConversationRow, conversation_id, populate_existing=True, with_for_update=True
    )
    if conversation is None:
        raise UnknownConversationError(conversation_id)

    method = VerificationMethod.EMAIL_AND_POSTAL_CODE
    failed = sum(
        event.type == EventType.VERIFICATION_COMPLETED and event.payload.get("verified") is False
        for event in log.read(conversation_id)
    )
    remaining = max(0, MAX_VERIFICATION_ATTEMPTS - failed)
    customer_id = _matching_customer(CommerceRepo(db), args) if remaining else None
    if conversation.identity_verified and conversation.customer_id != customer_id:
        customer_id = None

    verified = customer_id is not None
    if verified:
        conversation.customer_id = customer_id
        conversation.identity_verified = True
    elif remaining:
        remaining -= 1

    log.append(
        conversation_id,
        EventType.VERIFICATION_COMPLETED,
        at=clock.now(),
        payload={
            "verified": verified,
            "method": method.value,
            "order_id": args.order_id,
            "customer_id": customer_id,
            "attempts_remaining": remaining,
        },
    )
    return VerificationResult(
        verified=verified,
        method=method,
        customer_id=customer_id,
        attempts_remaining=remaining,
        message="Your identity is verified." if verified else "We could not verify your identity.",
    )


__all__ = ["verify_identity"]
