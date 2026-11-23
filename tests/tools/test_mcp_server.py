"""The MCP server exposes only the guarded surface: read tools + propose_action."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import Engine

from psa.clock import SimulatedClock
from psa.store import make_session_factory
from psa.tools import SimulatedStripe
from psa.tools.mcp_server import build_server
from tests.policy.helpers import NOW

pytestmark = pytest.mark.db


def test_mcp_server_exposes_only_guarded_tools(pg_engine: Engine) -> None:
    server = build_server(
        make_session_factory(pg_engine), clock=SimulatedClock(NOW), payments=SimulatedStripe()
    )
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "get_order",
        "list_customer_orders",
        "get_shipment_status",
        "get_customer_profile",
        "lookup_policy",
        "propose_action",
    }
    assert not names & {"issue_refund", "issue_store_credit", "cancel_order", "update_address"}
