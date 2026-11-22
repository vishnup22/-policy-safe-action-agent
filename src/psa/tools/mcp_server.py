"""MCP server exposing the GUARDED tool surface: read tools + propose_action.

External MCP clients get exactly what the guarded agent gets: they can look things up and
propose actions, and every proposal is decided by the policy engine. Write tools are never
exposed.

    PSA_CUSTOMER_ID=cus_000001 PSA_IDENTITY_VERIFIED=true uv run python -m psa.tools.mcp_server

Uses DATABASE_URL and STRIPE_SECRET_KEY (simulator when unset). Policy version: PSA_POLICY_VERSION.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from sqlalchemy.orm import Session, sessionmaker

from psa.clock import Clock, SystemClock
from psa.domain import SystemUnderTest
from psa.llm import ToolCall
from psa.runtime.factory import default_registry
from psa.runtime.ports import RuntimeConfig
from psa.store import EventLog, make_engine, make_session_factory, transaction
from psa.store.models import ConversationRow
from psa.tools import READ_TOOLS, FaultInjector, PaymentsGateway, ToolContext, gateway_from_env

DEFAULT_POLICY_VERSION = "2026.11.21-1"


def build_server(
    sessions: sessionmaker[Session] | None = None,
    clock: Clock | None = None,
    payments: PaymentsGateway | None = None,
) -> MCPServer:
    from psa.agent.agents import GuardedAgent
    from psa.executor import Executor
    from psa.policy import SessionContext

    clock = clock or SystemClock()
    sessions = sessions or make_session_factory(make_engine())
    registry = default_registry()
    config = RuntimeConfig(
        system=SystemUnderTest.GUARDED,
        policy_version=os.environ.get("PSA_POLICY_VERSION", DEFAULT_POLICY_VERSION),
    )
    payments = payments or gateway_from_env()
    executor = Executor(clock)
    customer_id = os.environ.get("PSA_CUSTOMER_ID") or None
    verified = os.environ.get("PSA_IDENTITY_VERIFIED", "false").lower() == "true"
    with transaction(sessions) as db:
        conversation_id = EventLog(db).start_conversation(at=clock.now(), customer_id=customer_id)
        row = db.get(ConversationRow, conversation_id)
        assert row is not None
        row.identity_verified = verified

    server = MCPServer(
        name="policy-safe-action-agent",
        instructions=(
            "Larkspur Goods support tools. Actions go through propose_action and store policy."
        ),
    )

    def call(tool: str, arguments: dict[str, Any]) -> str:
        with transaction(sessions) as db:
            policy = registry.get(config.policy_set, config.policy_version)
            ctx = ToolContext(
                db=db,
                clock=clock,
                session=SessionContext(conversation_id, customer_id, verified),
                policy=policy,
                payments=payments,
                faults=FaultInjector(),
            )
            agent = GuardedAgent(
                llm=None,  # type: ignore[arg-type]  # never called: we dispatch directly
                ctx=ctx,
                log=EventLog(db),
                executor=executor,
                policy=policy,
                max_steps=config.max_agent_steps,
            )
            output = agent._dispatch(ToolCall(call_id="mcp", name=tool, arguments=arguments))
            return output.content

    for name, tool in READ_TOOLS.items():

        def make(tool_name: str):  # type: ignore[no-untyped-def]
            def handler(arguments: dict[str, Any] | None = None) -> str:
                return call(tool_name, arguments or {})

            return handler

        server.tool(name=name, description=tool.spec.description)(make(name))

    @server.tool(
        name="propose_action",
        description="Propose an action (refund, store credit, cancel, address change, ticket, "
        "escalation, follow-up). The store policy engine decides whether it runs.",
    )
    def propose_action(action: str, args: dict[str, Any], justification: str) -> str:
        return call(
            "propose_action", {"action": action, "args": args, "justification": justification}
        )

    return server


if __name__ == "__main__":
    build_server().run()
