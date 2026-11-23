import pytest
from tests.store.conftest import schemas  # noqa: F401


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "load: opt-in API load tests (RUN_LOAD=1)")
