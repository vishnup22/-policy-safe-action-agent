"""Throwaway migrated PostgreSQL schema per trial; never resets the application schema."""

import secrets
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from psa.store import make_engine, make_session_factory

MIGRATION_LOCK = threading.Lock()
ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def trial_database(url: str) -> Iterator[sessionmaker[Session]]:
    schema = "psa_eval_" + secrets.token_hex(12)
    admin = make_engine(url)
    engine = make_engine(url, schema=schema)
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        with MIGRATION_LOCK, engine.begin() as conn:
            cfg = Config(str(ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(ROOT / "alembic"))
            cfg.attributes.update(connection=conn, configure_logger=False)
            command.upgrade(cfg, "head")
        yield make_session_factory(engine)
    finally:
        engine.dispose()
        if created:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
