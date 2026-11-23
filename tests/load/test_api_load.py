import os

import pytest
from evals.load import run_load
from tests.store.conftest import SchemaFactory

from psa.store import make_session_factory

pytestmark = [
    pytest.mark.load,
    pytest.mark.db,
    pytest.mark.skipif(os.environ.get("RUN_LOAD") != "1", reason="set RUN_LOAD=1 to opt in"),
]


def test_concurrent_conversations_and_approval_race(schemas: SchemaFactory) -> None:
    result = run_load(make_session_factory(schemas.create()), conversations=12, turns=3, workers=8)
    assert result.conversations == 12
    assert result.requests == 62
    assert result.approval_statuses == (200, 409)
    assert result.p95_latency_ms > 0
    print(f"API p95: {result.p95_latency_ms:.1f} ms across {result.requests} requests")
