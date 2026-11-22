"""Everything a tool needs for one call: DB session, clock, session identity, gateways."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from psa.clock import Clock
from psa.policy import PolicySet, SessionContext
from psa.store import CommerceRepo
from psa.tools.faults import FaultInjector
from psa.tools.payments import PaymentsGateway


@dataclass
class ToolContext:
    db: Session
    clock: Clock
    session: SessionContext
    policy: PolicySet
    payments: PaymentsGateway
    faults: FaultInjector

    @property
    def repo(self) -> CommerceRepo:
        return CommerceRepo(self.db)
