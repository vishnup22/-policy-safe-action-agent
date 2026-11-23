"""`build_runtime` — the RuntimeFactory used by the API and the eval runner."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from psa.clock import Clock
from psa.llm import LLMClient, client_from_env
from psa.policy import PolicyRegistry
from psa.runtime.agent_runtime import PolicySafeRuntime
from psa.runtime.ports import AgentRuntime, RuntimeConfig
from psa.tools import PaymentsGateway, gateway_from_env

POLICY_ROOT = Path(__file__).resolve().parents[3] / "policies"


@lru_cache(maxsize=4)
def default_registry(root: str = str(POLICY_ROOT)) -> PolicyRegistry:
    return PolicyRegistry.from_dir(Path(root))


def build_runtime(
    config: RuntimeConfig,
    *,
    sessions: sessionmaker[Session],
    clock: Clock,
    llm: LLMClient | None = None,
    payments: PaymentsGateway | None = None,
    registry: PolicyRegistry | None = None,
) -> AgentRuntime:
    """Satisfies `psa.runtime.ports.RuntimeFactory`. Extra keyword args are for tests/demos."""
    return PolicySafeRuntime(
        config,
        sessions=sessions,
        clock=clock,
        llm=llm or client_from_env("LLM"),
        payments=payments or gateway_from_env(),
        registry=registry or default_registry(),
    )
