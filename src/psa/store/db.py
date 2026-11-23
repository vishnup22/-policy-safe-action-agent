"""Database engine/session helpers and the declarative base."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://psa:psa@localhost:5433/psa"

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(url: str | None = None, *, schema: str | None = None, **kwargs: object) -> Engine:
    """Create an engine. `schema` pins search_path (used by tests for isolation)."""
    connect_args: dict[str, object] = {}
    if schema is not None:
        connect_args["options"] = f"-csearch_path={schema}"
    return create_engine(
        url or database_url(), pool_pre_ping=True, connect_args=connect_args, **kwargs
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session]) -> Iterator[Session]:
    """One unit of work: commit on success, roll back on any exception."""
    with factory() as session, session.begin():
        yield session
