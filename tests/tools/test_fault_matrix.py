import pytest
from sqlalchemy.orm import Session

from psa.clock import SimulatedClock
from psa.domain import EventType
from psa.executor.executor import ExecutionStatus, Executor
from psa.runtime.ports import FaultMode, ToolFault
from psa.store import CommerceRepo, EventLog
from psa.tools.context import ToolContext
from psa.tools.errors import ToolFailure
from psa.tools.faults import PAYMENTS_REFUND, FaultInjectingPayments, FaultInjector
from psa.tools.payments import SimulatedStripe
from psa.tools.write_tools import WRITE_TOOLS
from tests.policy.helpers import ALICE, NOW, V1, customer, order, refund, session
from tests.store.conftest import db, pg_engine, schemas  # noqa: F401

MODES = [
    (FaultMode.TIMEOUT, True),
    (FaultMode.ERROR_5XX, True),
    (FaultMode.RATE_LIMITED, True),
    (FaultMode.CARD_DECLINED, False),
]


@pytest.mark.parametrize(("mode", "retryable"), MODES)
@pytest.mark.parametrize("tool", list(WRITE_TOOLS))
def test_every_write_tool_supports_each_fault(tool: str, mode: FaultMode, retryable: bool) -> None:
    faults = FaultInjector([ToolFault(tool=tool, on_call=2, mode=mode)])
    faults.before_call(tool)
    faults.before_call("get_order")
    with pytest.raises(ToolFailure) as raised:
        faults.before_call(tool)
    assert raised.value.code == mode.value
    assert raised.value.retryable == retryable
    faults.before_call(tool)
    assert faults.calls(tool) == 3


@pytest.mark.db
@pytest.mark.parametrize(("mode", "retryable"), MODES)
@pytest.mark.parametrize("target", ["issue_refund", PAYMENTS_REFUND])
def test_refund_fault_records_attempts_and_preserves_idempotency(
    db: Session,  # noqa: F811
    mode: FaultMode,
    retryable: bool,
    target: str,
) -> None:
    action = refund()
    original = order()
    repo = CommerceRepo(db)
    repo.add_customer(customer())
    repo.add_order(original)
    log = EventLog(db)
    log.start_conversation(at=NOW, customer_id=ALICE, conversation_id=action.conversation_id)
    faults = FaultInjector([ToolFault(tool=target, on_call=1, mode=mode)])
    gateway = SimulatedStripe()
    clock = SimulatedClock(NOW)
    ctx = ToolContext(db, clock, session(), V1, FaultInjectingPayments(gateway, faults), faults)
    executor = Executor(clock)

    result = executor.execute(action, ctx=ctx, log=log, policy_version=V1.version)
    events = log.read(action.conversation_id)
    (failed,) = [event for event in events if event.type == EventType.ACTION_FAILED]
    assert failed.payload["attempt"] == 1
    assert failed.payload["retryable"] == retryable
    assert failed.payload["error"].startswith(f"{mode.value}:")
    if retryable:
        assert result.status == ExecutionStatus.EXECUTED
        assert result.attempts == 2
        again = executor.execute(action, ctx=ctx, log=log, policy_version=V1.version)
        assert again.status == ExecutionStatus.DUPLICATE
        assert faults.calls(target) == 2
        assert gateway.calls == 1
        assert len(gateway.receipts) == 1
        assert [e.type for e in log.read(action.conversation_id)][-2:] == [
            EventType.ACTION_FAILED,
            EventType.ACTION_EXECUTED,
        ]
    else:
        assert result.status == ExecutionStatus.FAILED
        assert result.attempts == 1
        assert faults.calls(target) == 1
        assert gateway.calls == 0
        assert all(event.type != EventType.ACTION_EXECUTED for event in events)
    stored = repo.get_order(original.order_id)
    assert stored is not None
    assert stored.amount_refunded_cents == (original.amount_paid_cents if retryable else 0)
