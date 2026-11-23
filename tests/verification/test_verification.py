import pytest
from sqlalchemy.orm import Session
from tests.policy.helpers import ALICE, BOB, NOW, ORDER, customer, order

from psa.clock import SimulatedClock
from psa.domain import MAX_VERIFICATION_ATTEMPTS, EventType, VerificationResult, VerifyIdentityArgs
from psa.store import CommerceRepo, EventLog
from psa.store.models import ConversationRow
from psa.verification import verify_identity

pytestmark = pytest.mark.db
OTHER_ORDER = "ord_bobby02"


@pytest.fixture
def log(db: Session) -> EventLog:
    repo = CommerceRepo(db)
    for customer_id, order_id in ((ALICE, ORDER), (BOB, OTHER_ORDER)):
        repo.add_customer(customer(customer_id))
        stored_order = order(order_id, customer_id=customer_id, country="CA")
        shipping = stored_order.shipping_address.model_copy(update={"postal_code": "K1A 0B1"})
        repo.add_order(stored_order.model_copy(update={"shipping_address": shipping}))
    return EventLog(db)


def verify(
    db: Session,
    log: EventLog,
    conversation_id: str,
    *,
    order_id: str = ORDER,
    email: str = f" {ALICE.upper()}@EXAMPLE.COM ",
    postal_code: str = " k1a0 b1 ",
) -> VerificationResult:
    return verify_identity(
        db,
        conversation_id,
        VerifyIdentityArgs(order_id=order_id, email=email, postal_code=postal_code),
        clock=SimulatedClock(NOW),
        log=log,
    )


def test_match_persists_identity_and_appends_one_event(db: Session, log: EventLog) -> None:
    conversation_id = log.start_conversation(at=NOW, customer_id=BOB)
    result = verify(db, log, conversation_id)
    assert result.verified
    assert result.customer_id == ALICE
    assert result.attempts_remaining == MAX_VERIFICATION_ATTEMPTS
    db.expire_all()
    row = db.get_one(ConversationRow, conversation_id)
    assert row.customer_id == ALICE
    assert row.identity_verified

    (completed,) = log.read(conversation_id)[1:]
    assert completed.type == EventType.VERIFICATION_COMPLETED
    assert completed.at == NOW
    assert completed.payload == {
        "method": "email_and_postal_code",
        "order_id": ORDER,
        "verified": True,
        "customer_id": ALICE,
        "attempts_remaining": MAX_VERIFICATION_ATTEMPTS,
    }


@pytest.mark.parametrize(
    "wrong",
    [{"email": f"{BOB}@example.com"}, {"postal_code": "62701"}, {"order_id": "ord_missing0"}],
    ids=["wrong-email", "customer-postal-instead-of-shipping", "missing-order"],
)
def test_mismatch_gives_generic_result(db: Session, log: EventLog, wrong: dict[str, str]) -> None:
    conversation_id = log.start_conversation(at=NOW)
    result = verify(db, log, conversation_id, **wrong)
    assert not result.verified
    assert result.customer_id is None
    assert result.attempts_remaining == MAX_VERIFICATION_ATTEMPTS - 1
    assert result.message == "We could not verify your identity."
    assert not db.get_one(ConversationRow, conversation_id).identity_verified
    assert log.read(conversation_id)[-1].payload == {
        "verified": False,
        "method": "email_and_postal_code",
        "order_id": wrong.get("order_id", ORDER),
        "customer_id": None,
        "attempts_remaining": MAX_VERIFICATION_ATTEMPTS - 1,
    }


def test_lockout_after_three_failures(db: Session, log: EventLog) -> None:
    conversation_id = log.start_conversation(at=NOW)
    for remaining in (2, 1, 0):
        attempt = verify(db, log, conversation_id, postal_code="BAD")
        assert not attempt.verified
        assert attempt.attempts_remaining == remaining
    blocked = verify(db, log, conversation_id)
    assert not blocked.verified
    assert blocked.attempts_remaining == 0
    assert len(log.read(conversation_id)) == 5
    assert not db.get_one(ConversationRow, conversation_id).identity_verified


def test_cannot_switch_verified_customer_or_unverify(db: Session, log: EventLog) -> None:
    conversation_id = log.start_conversation(at=NOW)
    assert verify(db, log, conversation_id).verified
    attempt = verify(db, log, conversation_id, order_id=OTHER_ORDER, email=f"{BOB}@example.com")
    assert not attempt.verified
    assert attempt.customer_id is None
    assert attempt.attempts_remaining == MAX_VERIFICATION_ATTEMPTS - 1
    row = db.get_one(ConversationRow, conversation_id)
    assert row.identity_verified
    assert row.customer_id == ALICE
    recheck = verify(db, log, conversation_id)
    assert recheck.verified
    assert recheck.attempts_remaining == MAX_VERIFICATION_ATTEMPTS - 1
