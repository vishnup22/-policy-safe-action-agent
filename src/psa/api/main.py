"""ASGI entrypoint: the HTTP API wired to the real policy-safe runtime.

    uv run uvicorn psa.api.main:app

Reads `Settings` (DEMO_PASSCODE, APP_AUTH_SECRET, ...) and DATABASE_URL from the
environment / `.env`. The LLM client is built from LLM_* variables but no model is
called until a conversation receives a message. Seed the world first:
`uv run python -m psa.seed load --seed 42 --now 2026-11-21T12:00:00Z`.
"""

from fastapi import FastAPI

from psa.api.app import create_app
from psa.api.auth import Settings
from psa.clock import SystemClock
from psa.runtime.factory import build_runtime
from psa.store import make_engine, make_session_factory


def build_app(settings: Settings | None = None, database_url: str | None = None) -> FastAPI:
    return create_app(
        runtime_factory=build_runtime,
        sessions=make_session_factory(make_engine(database_url)),
        clock=SystemClock(),
        settings=settings or Settings(),  # pyright: ignore[reportCallIssue] - fields come from env
    )


def __getattr__(name: str) -> FastAPI:
    # Built on first access so importing this module (tests, tooling) needs no env.
    if name == "app":
        app = build_app()
        globals()["app"] = app
        return app
    raise AttributeError(name)
