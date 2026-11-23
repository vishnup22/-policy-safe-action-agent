"""T4.5: the ASGI entrypoint and the eval runner use the real runtime factory."""

import importlib

import pytest
from evals.runner.__main__ import factories
from evals.runner.fake import EchoRuntime, StopSimulator
from evals.simulator import LLMUserSimulator
from pydantic import SecretStr

from psa.api.auth import Settings
from psa.runtime.factory import build_runtime

SETTINGS = Settings(demo_passcode=SecretStr("demo"), app_auth_secret=SecretStr("s" * 32))


def test_build_app_wires_real_runtime_without_calling_a_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    from psa.api import main

    seen: list[object] = []

    def spy(*args: object, **kwargs: object) -> object:
        runtime = build_runtime(*args, **kwargs)  # pyright: ignore[reportArgumentType]
        seen.append(runtime)
        return runtime

    monkeypatch.setattr(main, "build_runtime", spy)
    app = main.build_app(SETTINGS, "postgresql+psycopg://psa:psa@localhost:5433/psa")
    assert type(seen[0]).__name__ == "PolicySafeRuntime"
    paths = set(app.openapi()["paths"])
    assert {"/api/health", "/api/conversations", "/api/evals/runs"} <= paths


def test_importing_main_needs_no_environment() -> None:
    importlib.reload(importlib.import_module("psa.api.main"))


def test_runner_runtime_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    assert factories("fake") == (EchoRuntime, StopSimulator)
    monkeypatch.setenv("SIM_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("SIM_LLM_MODEL", "test-model")
    runtime_factory, simulator_factory = factories("real")
    assert runtime_factory is build_runtime
    assert isinstance(simulator_factory(), LLMUserSimulator)
