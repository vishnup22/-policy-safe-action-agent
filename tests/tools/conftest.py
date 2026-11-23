"""Share the Postgres and shop fixtures with tool tests."""

from tests.agent.conftest import sessions, shop  # noqa: F401
from tests.store.conftest import pg_engine, schemas  # noqa: F401
