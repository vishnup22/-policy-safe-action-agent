from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect

from psa.store import models as _models  # noqa: F401
from psa.store.db import Base
from tests.store.conftest import SchemaFactory, alembic_config

pytestmark = pytest.mark.db

EXPECTED_TABLES = {
    "alembic_version",
    "approvals",
    "conversations",
    "customers",
    "events",
    "follow_ups",
    "idempotency_keys",
    "llm_transcripts",
    "order_items",
    "orders",
    "refunds",
    "shipments",
    "store_credits",
}


def test_migration_creates_all_tables(pg_engine: Engine) -> None:
    assert set(inspect(pg_engine).get_table_names()) == EXPECTED_TABLES


def test_models_and_migrations_do_not_drift(pg_engine: Engine) -> None:
    with pg_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models differ from migrations; add a migration: {diff}"


def test_downgrade_and_upgrade_roundtrip(schemas: SchemaFactory) -> None:
    engine = schemas.create()
    with engine.begin() as conn:
        command.downgrade(alembic_config(conn), "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
