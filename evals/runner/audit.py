"""Independent execution-time oracle for ORM-backed runtimes.

A separate identity map reads the transaction's database state before commerce writes
flush. The oracle then evaluates ACTION_EXECUTED using that pre-effect snapshot and the
runner's active version/clock. It never reads the runtime's Decision/facts_snapshot.
"""

from collections.abc import Callable

from sqlalchemy import Connection, Table, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.dml import Delete, Insert, Update

from evals.runner.facts import WorldFacts
from psa.clock import Clock
from psa.domain import ActionIntent, Decision, DecisionOutcome, EventType
from psa.policy import PolicyRegistry, SessionContext, decide
from psa.seed import World
from psa.store import CommerceRepo
from psa.store.models import (
    ApprovalRow,
    ApprovalStatus,
    ConversationRow,
    CustomerRow,
    EventRow,
    OrderRow,
    StoreCreditRow,
)

EVAL_REVIEWER = "eval-operator"


class ExecutionAudit:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        world: World,
        registry: PolicyRegistry,
        clock: Clock,
        policy_set: str,
        version: Callable[[], str],
        *,
        allow_operator_approval: bool = False,
    ):
        self.sessions, self.world, self.registry = sessions, world, registry
        self.clock, self.policy_set, self.version = clock, policy_set, version
        self.decisions: dict[str, Decision] = {}
        self.allow_operator_approval = allow_operator_approval
        self.approved_executions: set[str] = set()
        self.intents: dict[str, ActionIntent] = {}
        self.snapshots: dict[int, dict[str, tuple[WorldFacts, SessionContext]]] = {}

    def capture(
        self, db: Session | Connection, intent: ActionIntent
    ) -> tuple[WorldFacts, SessionContext]:
        # Nested savepoint avoids closing/rolling back the runtime's outer transaction.
        connection = db.connection() if isinstance(db, Session) else db
        with Session(bind=connection, join_transaction_mode="create_savepoint") as reader:
            repo = CommerceRepo(reader)
            source = WorldFacts(self.world)
            order_id = getattr(intent.args, "order_id", None)
            if order_id:
                order = repo.get_order(order_id)
                source.orders.pop(order_id, None)
                if order is not None:
                    source.orders[order_id] = order
            conversation = reader.get(ConversationRow, intent.conversation_id)
            if conversation is None:
                raise ValueError("execution lacks durable session")
            customer_id = conversation.customer_id
            if customer_id:
                customer = repo.get_customer(customer_id)
                source.customers.pop(customer_id, None)
                if customer is not None:
                    source.customers[customer_id] = customer
            source.credits = [
                (row.customer_id, row.amount_cents, row.issued_at)
                for row in reader.scalars(select(StoreCreditRow))
            ]
            context = SessionContext(
                intent.conversation_id, customer_id, conversation.identity_verified
            )
            return source, context

    def before_flush(self, db: Session, flush_context: object, instances: object) -> None:
        rows = [row for row in db.new if isinstance(row, EventRow)]
        for row in rows:
            if row.type == EventType.ACTION_PROPOSED:
                intent = ActionIntent.model_validate(row.payload["intent"])
                self.intents[intent.intent_id] = intent
        pending = self.snapshots.setdefault(id(db.connection()), {})
        if any(
            isinstance(row, (OrderRow, CustomerRow, StoreCreditRow)) for row in (*db.new, *db.dirty)
        ):
            for identifier, intent in self.intents.items():
                if identifier not in pending:
                    pending[identifier] = self.capture(db, intent)
        for row in rows:
            if row.type != EventType.ACTION_EXECUTED:
                continue
            intent = self.intents.get(row.payload.get("intent_id", ""))
            if intent is None:
                continue
            source, context = pending.get(intent.intent_id) or self.capture(db, intent)
            decision = decide(
                intent,
                self.registry.get(self.policy_set, self.version()),
                source=source,
                session=context,
                clock=self.clock,
            )
            self.decisions[row.event_id] = decision
            if (
                self.allow_operator_approval
                and decision.outcome == DecisionOutcome.REQUIRE_APPROVAL
            ):
                approved = db.scalar(
                    select(ApprovalRow.approval_id).where(
                        ApprovalRow.conversation_id == intent.conversation_id,
                        ApprovalRow.intent_id == intent.intent_id,
                        ApprovalRow.status == ApprovalStatus.APPROVED,
                        ApprovalRow.reviewer == EVAL_REVIEWER,
                    )
                )
                if approved is not None:
                    self.approved_executions.add(row.event_id)
            pending.clear()

    def before_execute(
        self,
        connection: Connection,
        clause: object,
        multiparams: object,
        params: object,
        options: object,
    ) -> None:
        if (
            isinstance(clause, (Insert, Update, Delete))
            and isinstance(clause.table, Table)
            and clause.table.name
            in {
                "orders",
                "order_items",
                "customers",
                "store_credits",
            }
        ):
            pending = self.snapshots.setdefault(id(connection), {})
            for identifier, intent in self.intents.items():
                if identifier not in pending:
                    pending[identifier] = self.capture(connection, intent)

    def __enter__(self) -> "ExecutionAudit":
        event.listen(self.sessions.class_, "before_flush", self.before_flush)
        event.listen(self.sessions.kw["bind"], "before_execute", self.before_execute)
        return self

    def __exit__(self, *args: object) -> None:
        event.remove(self.sessions.class_, "before_flush", self.before_flush)
        event.remove(self.sessions.kw["bind"], "before_execute", self.before_execute)
        self.snapshots.clear()
