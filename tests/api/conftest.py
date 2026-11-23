"""Reusable DB factories preserve the store fixture's per-test rollback."""

import pytest
from sqlalchemy.orm import Session, sessionmaker
from tests.store.conftest import db, pg_engine, schemas  # noqa: F401


@pytest.fixture
def sessions(db: Session) -> sessionmaker[Session]:  # noqa: F811 - pytest fixture injection
    return sessionmaker(
        bind=db.connection(), expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
