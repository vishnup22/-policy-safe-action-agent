"""Postgres fixtures. Each test session migrates a throwaway schema; each test rolls back.

Tests are skipped (not failed) when DATABASE_URL is unreachable, so the suite still runs
without Docker. CI always provides Postgres.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from psa.store.db import database_url, make_engine

ROOT = Path(__file__).resolve().parents[2]


def _reachable(url: str) -> bool:
    probe = create_engine(url, connect_args={"connect_timeout": 2})
    try:
        with probe.connect():
            return True
    except OperationalError:
        return False
    finally:
        probe.dispose()


def alembic_config(connection: object) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.attributes["configure_logger"] = False
    cfg.attributes["connection"] = connection
    return cfg


class SchemaFactory:
    """Creates isolated, migrated schemas and drops them at the end of the session."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.admin = create_engine(url)
        self.created: list[tuple[str, Engine]] = []

    def create(self, *, migrate: bool = True) -> Engine:
        schema = f"psa_test_{secrets.token_hex(4)}"
        with self.admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = make_engine(self.url, schema=schema)
        if migrate:
            with engine.begin() as conn:
                command.upgrade(alembic_config(conn), "head")
        self.created.append((schema, engine))
        return engine

    def drop_all(self) -> None:
        for schema, engine in self.created:
            engine.dispose()
            with self.admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        self.admin.dispose()


@pytest.fixture(scope="session")
def schemas() -> Iterator[SchemaFactory]:
    url = database_url()
    if not _reachable(url):
        pytest.skip(
            f"Postgres not reachable at {url} "
            "(start it: docker compose -f infra/docker-compose.yml up -d db)"
        )
    factory = SchemaFactory(url)
    yield factory
    factory.drop_all()


@pytest.fixture(scope="session")
def pg_engine(schemas: SchemaFactory) -> Engine:
    return schemas.create()


@pytest.fixture
def db(pg_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test."""
    conn = pg_engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()
