"""Identity verification service — contract stub (T5.0); Lane H (Codex) implements T6.2.

Contract (see `psa.domain.verification`):

    verify_identity(db, conversation_id, args, *, clock, log) -> VerificationResult

- Looks up `args.order_id`; verified iff the order exists AND its customer's email
  matches `args.email` (case-insensitive, trimmed) AND the order's shipping postal code
  matches `args.postal_code` (case/space-insensitive). Facts come from the DB only.
- At most `MAX_VERIFICATION_ATTEMPTS` failed attempts per conversation; after that it
  returns verified=False, attempts_remaining=0 without checking.
- Appends `verification_requested` {method, order_id} then `verification_completed`
  {verified, method, customer_id|null, attempts_remaining} to the event log.
- On success sets ConversationRow.customer_id and identity_verified=True. It never
  un-verifies and never switches an already-verified conversation to another customer
  (returns verified=False for a different customer).
- The message never says which field was wrong.
"""

from sqlalchemy.orm import Session

from psa.clock import Clock
from psa.domain import VerificationResult, VerifyIdentityArgs
from psa.store import EventLog


def verify_identity(
    db: Session, conversation_id: str, args: VerifyIdentityArgs, *, clock: Clock, log: EventLog
) -> VerificationResult:
    raise NotImplementedError("T6.2 (Lane H) implements identity verification")


__all__ = ["verify_identity"]
